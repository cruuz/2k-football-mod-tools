# State Farm Stadium (experimental)

Build option `modern_state_farm`, off in every preset. It writes the Arizona Cardinals' State Farm Stadium (Glendale,
opened 2006; Eisenman Architects with Populous; the roof by Walter P Moore and Birdair) into the Cardinals' venue record
s00 (retail Arizona Stadium), all nine bundles (day, afternoon and night; dry, rain and snow), and names the s00 row
State Farm Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder on the U.S. Bank Stadium model's parts: the
  red bowl in four stacks (the 100, 200, loft and 400 levels on the sides, lower at both ends), crowd billboards in the
  retail convention cut at every aisle, the ribbons and the field wall's pads in plain type. The fabric roof drawn open:
  the dome curving down from the crown (the rails' tangent point, 206 ft over grade) to the drum with its radial ribs,
  the opening over the whole field between the two Brunel trusses, the two retractable panels parked over the ends on
  their tracks, the floodlights. The north board (30 x 117 ft) and the south board on the game's live feed (a crop at
  each board's own aspect, never stretched) with the game's digits on their wings. Outside, on the OpenStreetMap
  outline: the silver barrel-cactus drum with its petals and dark slots, the glass gates, the wordmark on the drum and on
  the roof, the lots, roads and blocks, the desert and the White Tank Mountains. The retail cityscape is collapsed (the
  surroundings live in the stadium scene); the sky is the engine's own (an open-air row). The sideline props, pylons,
  yard markers, banners and digits stay from retail. The scene fits the retail stored span of every bundle and decodes
  smaller than retail.
- **The intro cameras**: five new shots on s00's own camera channels: rising along the drum at the west gate, a crane
  over midfield toward the open roof and the north board, a pan from the east upper deck, an aerial over the open roof
  and the parked panels, and field level behind the south end zone.
- **The field**: when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Cardinals' 2026 end
  zones in the retail field's own textures (each end its own, in each bundle's rain and snow looks) and a new midfield
  quad in the field scene carrying the folder's midfield; the grass and the apron on the Modern playing surfaces palette
  for s00 in each bundle's own light (that option's own painter and fit; never tuned here). Modern playing surfaces, run
  after this option, leaves the field's paint as it is.
- **The s00 row**: State Farm Stadium, Glendale, AZ, capacity 63,400; the indoor word stays 0 (the roof drawn open: rain
  and snow fall as the retail row lets them); the grass word and the Tempe climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s00 to it.

## Sources

- Facts: Wikipedia "State Farm Stadium" (fetched 2026-09-27); Walter P Moore (the roof: two panels about 258 x 275 ft on
  rails at 15 degrees to a tangent point 206 ft over grade, travelling 180 ft; two Brunel trusses each spanning 700 ft);
  Daktronics 2022 (the north board); RateYourSeats' Cardinals chart (the benches, the boards).
- Plan: OpenStreetMap relation 7370103 and its neighbours (ODbL 1.0), in `data/nfl2k5_state_farm_model/footprint.json`.
- Photos: Wikimedia Commons (the aerials with the roof open and closed, the bowl by day and night, the roof from
  below, the drum) and the orthophotos (reference only).
- Art: `tools/nfl2k5_state_farm_model_art.py`, deterministic; the State Farm Stadium wordmark is cut from its Wikimedia
  Commons public-domain file (never redrawn); plain type otherwise; no players.

## Edition pack

`tools/nfl2k5_state_farm_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

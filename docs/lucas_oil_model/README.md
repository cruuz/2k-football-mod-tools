# Lucas Oil Stadium (experimental)

Build option `modern_lucas_oil`, off in every preset. It writes the Indianapolis Colts' Lucas Oil Stadium (Indianapolis,
opened 2008; HKS with Walter P Moore) into the Colts' venue record s11 (retail RCA Dome), all nine bundles (day,
afternoon and night; dry, rain and snow), and names the s11 row Lucas Oil Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder on the U.S. Bank Stadium model's parts: the
  blue bowl in four stacks (the sidelines and the south end with the lower bowl, the club tier, the suites and the upper
  deck; the north end the lower levels under the window), crowd billboards in the retail convention cut at every aisle,
  the ribbons and the field wall's pads in plain type. The gabled roof on the field's axis drawn closed (the two
  retractable panels either side of the ridge, the fixed roof beyond them, the ridge, rail and transverse trusses under
  it, the floodlights, LUCAS OIL STADIUM on the panels). The north window (214 x 88 ft) over the north stands with
  downtown's towers beyond it, the stadium's wordmark over it and the Colts' banners. The two 37 x 97 ft boards in the
  north-west and south-east corners on the game's live feed (a crop at each board's own aspect, never stretched) with the
  game's digits on their wings and two auxiliary boards over each. Outside, on the OpenStreetMap outline: the brick and
  limestone fieldhouse with its arched window bays, the four corner towers, the wordmark on the ends, the lots, streets,
  rail, blocks and downtown. s11 has no cityscape chunk. The sideline props, pylons, yard markers, banners and digits
  stay from retail. The scene fits the retail stored span of every bundle and decodes smaller than retail.
- **The intro cameras**: five new shots on s11's own camera channels: a crane on the axis toward the north window, a
  level pass along the west upper level, a pan from the east upper deck, the north-east corner and the window from the
  street, and an aerial push over the gabled roof from the south-east.
- **The field**: when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Colts' 2026 end zones
  and midfield horseshoe in the retail field's own textures (each end its own); the turf and the apron on the Modern
  playing surfaces palette for s11 (that option's own painter and fit: the synthetic look, the 2026 broadcast measured
  at Lucas Oil Stadium, the dome light; never tuned here). Modern playing surfaces, run after this option, leaves the
  field's paint as it is.
- **The s11 row**: Lucas Oil Stadium, Indianapolis, IN, capacity 67,000; the indoor word stays 1 (the roof drawn closed:
  no rain or snow); the turf word and the flat climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s11 to it.

## Sources

- Facts: Wikipedia "Lucas Oil Stadium" (fetched 2026-09-27); lucasoilstadium.com's background and history (the roof
  panels, the window, the boards, the capacity, the field 25 ft below the street); Uni-Systems (the gabled roof and the
  window wall); RateYourSeats' 2026 Colts chart (the benches, the boards' corners).
- Plan: OpenStreetMap way 27258709 and its neighbours (ODbL 1.0), in `data/nfl2k5_lucas_oil_model/footprint.json`.
- Photos: Wikimedia Commons (the 2024 stadium tour, a 2023 Colts game, the 2022 title game, the exteriors and aerials;
  one camera pose solved from the field lines) and the orthophotos (reference only).
- Art: `tools/nfl2k5_lucas_oil_model_art.py`, deterministic; the Lucas Oil Stadium wordmark is cut from its Wikimedia
  Commons public-domain file (never redrawn); plain type otherwise; no players.

## Edition pack

`tools/nfl2k5_lucas_oil_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

# Hard Rock Stadium (experimental)

Build option `modern_hard_rock`, off in every preset. It writes the Miami Dolphins' Hard Rock Stadium (Miami Gardens,
FL; opened 1987 as Joe Robbie Stadium; the 2015 to 2016 modernization by HOK with Thornton Tomasetti) into the Dolphins'
venue record s14 (retail Pro Player Stadium), all nine bundles (day, afternoon and night; dry, rain and snow), and names
the s14 row Hard Rock Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the aqua bowl in four stacks: the 100 level from the field wall (the 2015 renovation brought the sideline seats 25 ft
  closer), the club tier and the suites, and the upper deck (its extent read from the retail scene). Crowd billboards
  in the retail convention, cut at every aisle, and the ribbons on the fascias.
- **The shade canopy** over the seats, its plan measured on the Esri orthophoto (reference only; the roof features
  centred to remove the relief displacement) and its heights on a solved photo pose (the 2026 press-box photo, 1.3 px):
  the white roof on its white steel from 38.5 m to 47.9 m over the field, the translucent ETFE ring round the opening
  over the field, the opening's edge truss with the lamps under it and the arches over its four sides, the four white
  spires to 108.8 m (357 ft over the ground) with their sixty-four cables, and the eight super columns under the corners.
- **The four corner boards** (112 x 50 ft each, fitted on the solved pose at 2.9 px, mirror images turned in toward
  the field) on the `jumbo_tron` material the game draws its live feed into (a crop of the feed at the picture's own
  aspect, never stretched, at a loop gain of about 1), each between two stat panels, the game's digits on the south-west
  board's. Seats under a board stop below it.
- **Outside**, on the OpenStreetMap outline: the white concrete building under the canopy with its spiral ramps at the
  corners, the venue's name as plain type on the canopy's fascia over both sidelines; the surroundings from the shared
  environment kit (`mod_editor/core/nfl2k5_stadium_environment.py`, st3) outside the plaza: the lots with their parked
  cars, the roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band at
  1,800 m (the terrain's ridges and the tall buildings round the site). The cityscape chunk is collapsed (the
  surroundings live in the stadium scene). The sideline props, pylons, yard markers, banners and digits stay from
  retail; the field-level cloths take the 2026 league sheet. The scene fits the retail stored span of every bundle and
  decodes smaller than retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s14's own camera channels (each wants 0 where its camera carries no
  component), two of them outside.
- **The field**: natural grass mown in 5-yard bands (the retail grass quad's UVs remapped in place), the grass outside
  the field of play, and, when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Dolphins' 2026
  end zones (each end on its own retail textures) and midfield composed over clean grass. With Modern playing surfaces
  on (run after it), the grass takes that option's palette for s14.
- **The s14 row**: Hard Rock Stadium, Miami, FL (the 2026 venue names' strings, so the two compose in either order),
  capacity 64,767; the indoor word stays 0 (the canopy shades the seats and leaves the field open: rain falls on it);
  the grass word and the climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s14 to it and lends it the Dolphins' field art.

## Sources

- Facts: Wikipedia "Hard Rock Stadium" (fetched 2026-09-28); the Dolphins' 2016 modernization sheet; Structure
  magazine on the canopy's structure.
- Plan: OpenStreetMap (the pitch, bearing 121.4 degrees, the building; ODbL 1.0) in
  `data/nfl2k5_hard_rock_model/footprint.json`; the surroundings in the kit's layout
  `data/nfl2k5_stadium_environment/s14.json` (OpenStreetMap, ODbL 1.0; the Terrain Tiles elevation set); the Esri World
  Imagery orthophoto for the canopy's plan (measured only, nothing of it is shipped).
- Photos: Wikimedia Commons (2016 to 2026), one of them with a solved camera pose (reference only).
- Art: `tools/nfl2k5_hard_rock_model_art.py`, deterministic; plain type only, no logos or players.

## Edition pack

`tools/nfl2k5_hard_rock_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

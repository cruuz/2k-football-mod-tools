# EverBank Stadium (experimental)

Build option `modern_everbank`, off in every preset, with its sub-option `modern_everbank_construction` (on by default).
It writes the Jacksonville Jaguars' EverBank Stadium (Jacksonville, FL; opened 1995; the 2014 boards and pools, the 2016
to 2017 clubs and Daily's Place) into the Jaguars' venue record s12 (the retail 2004 ALLTEL Stadium), all nine bundles
(day, afternoon and night; dry, rain and snow), and names the s12 row EverBank Stadium with the season's capacity.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`): the
  100 level from the field wall, the 200 level's club rows and glass on the sidelines and at the south end, the 400 level
  over the sidelines and the north end. Crowd billboards in the retail convention, cut at every aisle, and the ribbons on
  the fascias. The heights are a design reading of the retail scene and the 2025 orthophoto.
- **The end zone boards** (2014, Wikipedia: 362 ft long; 60 ft high) on the `jumbo_tron` material the game draws its live
  feed into (a crop of the feed at the picture's own aspect, never stretched, at a loop gain of about 1), each between two
  stat panels, the game's digits on the south board's; their dark housings carry the name as plain type on their backs.
  Seats under a board stop below it.
- **The north end's pool deck** (2014: two wading pools), the light banks on their great white lattice towers leaning in
  over the sideline decks (three a side, the 2010 to 2020 exteriors), the boards' white lattice frames, the building on
  OpenStreetMap's outline, Daily's Place under its white fabric roof south of the stadium; the surroundings from the
  shared environment kit (`mod_editor/core/nfl2k5_stadium_environment.py`, st3) outside the plaza: the lots with their
  parked cars, the roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the haze and the horizon
  band at 1,800 m (the terrain's ridges and the tall buildings round the site). The cityscape chunk is collapsed (the
  surroundings live in the stadium scene). The sideline props, pylons, yard markers, banners and digits stay from
  retail; the field-level cloths take the 2026 league sheet. The scene fits the retail stored span of every bundle and
  decodes smaller than retail; nothing on the disc moves.
- **The 2026 construction** (`modern_everbank_construction`, on by default: the season as it stands; jaguars.com
  2026-02-25 and NFL.com, August 2026): the 400 level stripped to bare concrete risers with no crowd (22,005 of its seats
  offline), the canopy's steel trusses going up round the outside, three tower cranes just outside the stadium, the light
  banks lowered into the upper section, the north pool deck closed behind site fencing with its pools drained, and safety
  netting along the stripped decks. The construction's geometry is a design reading of the reports and the 2025
  orthophoto. Off, the model is the 2025 stadium.
- **The intro cameras**: five new shots on s12's own camera channels (each wants 0 where its camera carries no
  component), two of them outside.
- **The field**: natural grass mown in 5-yard bands (the retail grass quad's UVs remapped in place), the grass outside
  the field of play, and, when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Jaguars' 2026
  end zones (each end on its own retail textures) and midfield composed over clean grass. With Modern playing surfaces
  on (run after it), the grass takes that option's palette for s12.
- **The s12 row**: the 2026 venue names' strings (EverBank Stadium, Jacksonville, FL; the two compose in either order),
  capacity 42,507 with the construction (SOURCED, standing room included) or 67,814 without (the 2025 stadium); the
  indoor word stays 0 (open air), the grass word and the climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s12 to it and lends it the Jaguars' field art.

## Sources

- Facts: Wikipedia "EverBank Stadium" (fetched 2026-09-28); jaguars.com "Jaguars Provide 2026 Stadium and Ticketing
  Updates" (2026-02-25); NFL.com on the 2026 season's construction (August 2026); the seating guides for the visitors'
  bench on the east side.
- Plan: OpenStreetMap (the pitch, way 172665883, bearing 191 degrees; the stadium's outline, way 27258894; Daily's
  Place, way 628324216; ODbL 1.0) in `data/nfl2k5_everbank_model/footprint.json`; the surroundings in the kit's layout
  `data/nfl2k5_stadium_environment/s12.json` (OpenStreetMap, ODbL 1.0; the Terrain Tiles elevation set); the Esri World
  Imagery orthophoto of the 2025 site for the plan and the construction's places (measured only, nothing of it is
  shipped).
- Art: `tools/nfl2k5_everbank_model_art.py`, deterministic; plain type only, no logos or players; the lattices and
  meshes are drawn see-through.

## Edition pack

`tools/nfl2k5_everbank_model_pack.py SOURCE MASTERS OUT [--art-root DIR] [--classic]` writes the 4x pack manifest keyed
on the model's own scene layout; build it against the catalog of the disc that will be played (the same construction
choice as the disc).

EXPERIMENTAL and UNWITNESSED in game.

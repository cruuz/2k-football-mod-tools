# Levi's Stadium (experimental)

Build option `modern_levis`, off in every preset. It writes the San Francisco 49ers' Levi's Stadium (Santa Clara,
opened 2014; HNTB; the 2025 renovation's 4K video boards) into the 49ers' venue record s25 (retail San Francisco Park),
all nine bundles (day, afternoon and night; dry, rain and snow), and names the s25 row Levi's Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the red bowl in four stacks (west, the 100 and 200 levels under the suite tower; east, the 100 and 200 levels, the
  loge glass and the steep upper deck; the two ends, the 100 and 200 levels and an upper tier), with crowd billboards
  in the retail convention, cut at every aisle, the WELCOME TO LEVI'S STADIUM ribbon over the 100 level and the lively
  ribbons on the upper fascias. The suite tower along the west sideline: the club level's glass over the 200 level,
  four suite levels behind white balconies with glass rails, the teal press level leaning out, the roof (white toward
  the field, the green roof, the solar strip along the back) and the light truss on its front edge. The light truss on
  the east upper deck's rim. The two end-zone 4K boards on steel legs over the end stands, west of the field axis (the
  south board measured on a solved photo pose), the game's live feed over the middle of each (a crop of the feed
  picture at its own aspect, never stretched) between two stat panels carrying the game's digits, and a plain-type
  LEVI'S STADIUM sign on top. Outside, on the OpenStreetMap outline: the tower's precast west face with its glass
  curtain, the name and a club banner (plain type), the concourse base and the open white steel frame round the other
  sides with the concourse decks behind it; the plaza, parking, Tasman Drive, the light rail, the creek, the neighbours
  and the Diablo Range's hills on the horizon. The cityscape chunk is collapsed (the surroundings live in the stadium
  scene). The sideline props, pylons, yard markers, banners and digits stay from retail; the field-level cloths take
  the 2026 league sheet. The scene fits the retail stored span of every bundle and decodes smaller than retail; nothing
  on the disc moves.
- **The intro cameras**: five new shots on s25's own camera channels (each wants 0 where its camera carries no
  component): the approach from the west lots onto the tower's face, a crane on the axis behind the south end zone,
  a level pass along the east rim toward the tower, a pan over the south-west corner, and field level in the north end
  zone turning toward the south board.
- **The field**: natural grass mown in 5-yard bands (the retail grass quad's UVs remapped in place), the grass outside
  the field of play, and, when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the 49ers' 2026
  end zones (each end on its own retail textures) and midfield composed over clean grass.
- **The s25 row**: Levi's Stadium, Santa Clara, CA, capacity 68,500; the indoor word stays 0 (open: rain and snow fall
  in those bundles); the grass word and the climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s25 to it.

## Sources

- Facts: Wikipedia "Levi's Stadium" (fetched 2026-09-25); the 2025 board facts from ANC and the trade press (9,120 x
  2,400 pixels, 39 million the pair); the seating guides for the benches (the 49ers on the west side).
- Plan: OpenStreetMap relation 14507664 and way 357300430 and their neighbours (ODbL 1.0), in
  `data/nfl2k5_levis_model/footprint.json`.
- Photos: Wikimedia Commons (the 2014 interiors and panoramas, the 2019 panorama, the 2016 satellite view, Super Bowl
  LX on 2026-02-08 with its camera pose solved from the goalposts and the field's corners, the 2026 World Cup) and the
  49ers' 2026 galleries (reference only).
- Art: `tools/nfl2k5_levis_model_art.py`, deterministic; plain type only, no logos or players.

## Edition pack

`tools/nfl2k5_levis_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the model's
own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

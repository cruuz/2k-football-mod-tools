# Highmark Stadium (experimental)

Build option `modern_highmark`, off in every preset. It writes the Buffalo Bills' new Highmark Stadium (Orchard Park,
opened 2026) into the Bills' venue record s03 (retail Ralph Wilson Stadium), all nine bundles (day, afternoon and
night; dry, rain and snow), and names the s03 row Highmark Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the bowl in its four stacks (west: the 100 level, two suite levels, the VIP boxes, the 300 and 400 levels; east: the
  100 level, the LED ribbon, the two 200-level club tiers with the loge band, the steep 400 level; north: the
  field-level club under the GA+ concourse 12 ft above the field, sections 121 to 125, the 22-row 300 level; south:
  38 rows, the 200 level and the 400 level), the upper decks cantilevered over the tiers below; crowd billboards in
  the retail convention, cut at every aisle; seats fading from red at each tier's front rows to royal at the back.
  The canopy covers the stands and rises toward the field, with its underside, floodlights and blue LED lines seen
  from the stands; two end-zone video boards carry the game's live feed (a crop of the feed picture at the board's own
  aspect) under the Highmark Stadium signs; the facade stands on the OpenStreetMap outline (folded silver-grey panels
  over a dark base band, the black north portal with the white wordmark, the charcoal wordmark on the other aspects);
  outside, the plaza, parking, roads and the old stadium's cleared site across Abbott Road. The sideline props,
  pylons, yard markers, banners and digits stay from retail. The cityscape is folded into the stretch; the scene fits
  the retail stored span of every bundle and decodes smaller than retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s03's own camera channels (each wants 0 where its camera carries no
  component): the exterior from the south-west, a level pan across the east stands, the bowl from above the west side,
  the approach from the south onto the roof, and the north end from the south end zone.
- **The field**: Kentucky bluegrass mown in 5-yard bands (the retail turf quad's UVs remapped in place), the grass
  outside the field of play, and, when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Bills'
  2026 end zones and midfield composed over clean grass; when the folder carries a south set (the league project's
  2026 end-line stencils differ by end), each end takes its own panels, one end in each half of the three shared
  panel textures. Rain and snow looks are tinted from the dry art. The field is
  composed before the Modern colour grade when that option is on. The surface word stays turf.
- **The s03 row**: Highmark Stadium, Orchard Park, NY, capacity 60,108; open air, so rain and snow still fall; the
  climate is retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s03 to it, as it leaves the MetLife and SoFi
records to theirs.

## Sources

- Facts: Wikipedia "Highmark Stadium" (fetched 2026-09-25); Populous project page; Dezeen 2026-08-14.
- Plan: OpenStreetMap way 1339149058 and its neighbours (ODbL 1.0), in `data/nfl2k5_highmark_model/footprint.json`.
- Seat plan: the ticketing seat map's sections and row counts (reference only, not shipped).
- Photos: Wikimedia Commons (Dekema 2026, CC BY-SA 4.0 and CC0) and the Bills' 2026 galleries (reference only).
- Art: `tools/nfl2k5_highmark_model_art.py`, deterministic; the Highmark Stadium wordmark is cut from the official
  logo (en.wikipedia `File:HighmarkStadium.svg`), never redrawn; the Bills' marks come from the 2026 team folders.

## Edition pack

`tools/nfl2k5_highmark_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

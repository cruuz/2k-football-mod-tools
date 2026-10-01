# AT&T Stadium (experimental)

Build option `modern_att`, off in every preset. It writes the Dallas Cowboys' AT&T Stadium (Arlington, opened 2009; HKS)
into the Cowboys' venue record s07 (retail Texas Stadium), all nine bundles (day, afternoon and night; dry, rain and
snow), and names the s07 row AT&T Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the bowl with its sideline stack (the lower bowl, the club level under its ribbon, the suite levels behind glass,
  the 300 level and the tall upper deck) and its end stack (the lower end-zone seats and the six stepped Party Pass
  decks with their glass railings, in front of the glass end walls); navy and charcoal seats with crowd billboards in
  the retail convention, cut at every aisle. The centre-hung board over midfield: two sideline screens (about 160 x 72
  ft) and two end screens (about 51 x 29 ft) on the game's live feed (a crop of the feed picture at each screen's own
  aspect, never stretched), a black housing with an LED ring and four cables; the game's score and clock digits on its
  ends. The dome on the leaning glass facade: dark steel from below with white trusses, the operable panels closed
  as the bright corridor between the two arches, which run along the field over the dome from their feet outside the
  end walls and hang below the panels inside. Outside, the glass curtain wall on the OpenStreetMap outline, the glass
  end walls, the plaza, parking, roads and nearby buildings. The sideline props, pylons, yard markers, banners and
  digits stay from retail; the field-level cloths take the 2026 league sheet. s07 carries no cityscape; the scene fits
  the retail stored span of every bundle and decodes smaller than retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s07's own camera channels (each wants 0 where its camera carries no
  component): the exterior from the south-east plaza, a crane on the axis in the east end zone, the board from over
  the west end at its top's height, the approach from the east over the arches, and field level in the west end zone
  turning onto the east end.
- **The live feed**: the board's four screens use retail's `jumbo_tron` material, and the game draws its own previous
  frame (640 x 448) into it, so a screen in view shows itself. The screens' vertex colour is 116, a loop gain of about
  1 (the combiner doubles it: st2 lab 2 measured 2.0 to 2.3 times at 245), and no flyover shot fills more than a
  quarter of the picture with feed (pass 1's close pass filled 57 to 65 percent and the board flooded white).
- **The field**: turf in light and dark 5-yard bands (the retail turf quad's UVs remapped in place), the turf outside
  the field of play, the retail TEXAS STADIUM field marks cleared, and, when the 2026 venue art folder is given (the
  Build's `modern_venues_2026`), the Cowboys' 2026 end zones and midfield composed over clean turf.
- **The s07 row**: AT&T Stadium, Arlington, TX, capacity 80,000; the indoor word stays 1 (the roof is closed: no rain
  or snow falls, as retail); the turf word and the climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s07 to it.

## Sources

- Facts: Wikipedia "AT&T Stadium" (fetched 2026-09-25).
- Plan: OpenStreetMap way 47086748 and its neighbours (ODbL 1.0), in `data/nfl2k5_att_model/footprint.json`.
- Photos: Wikimedia Commons (the Dec 2025 interior, the 2022 interior and roof photos, the 2018 aerial, the 2009 and
  2010 photos) and the Cowboys' 2026 galleries (reference only).
- Art: `tools/nfl2k5_att_model_art.py`, deterministic; plain type and plain stars only, no logos.

## Edition pack

`tools/nfl2k5_att_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the model's
own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

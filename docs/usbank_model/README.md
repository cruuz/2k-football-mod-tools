# U.S. Bank Stadium (experimental)

Build option `modern_usbank`, off in every preset. It writes the Minnesota Vikings' U.S. Bank Stadium (Minneapolis,
opened 2016; HKS) into the Vikings' venue record s15 (retail H. H. H. Metrodome), all nine bundles (day, afternoon and
night; dry, rain and snow), and names the s15 row U.S. Bank Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the purple bowl in four stacks (the two sides and the east end with the lower bowl, the club tier, the suites'
  glass and the upper deck; the west end the lower bowl alone, open to the Legacy Gate), with crowd billboards in the
  retail convention, cut at every aisle, the ribbons on the fascias and the club's plain-type bands. The fixed roof on
  its ridge truss 10 m north of the field's axis (the ridge rising from the east end to the prow): the pale ETFE south
  of it and the dark opaque half north of it, both falling to level gutters; the open queen's post trusses and the
  ridge truss under it, the rows of floodlights, and clerestory windows under the roof all round. The Legacy Gate's
  glass wall at the west end (reflective outside, see-through inside, downtown's towers beyond it) and the prow's blade
  with the U.S. Bank Stadium wordmark and the display below it. The west board (68 x 120 ft with its wings, the header
  over it) and the east board (51 x 88 ft at the club level) on the game's live feed (a crop of the feed picture at
  each board's own aspect, never stretched), with the game's digits on the wings. The east end's banner (the two-line
  wordmark on blue), the United States flag hung vertically, and the 3M and Land O'Lakes panels. Outside, on the
  OpenStreetMap outline: the dark facade over a glass base, the plaza, parking, roads, blocks and downtown's towers.
  s15 has no cityscape chunk. The sideline props, pylons, yard markers, banners and digits stay from retail. The scene
  fits the retail stored span of every bundle and decodes smaller than retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s15's own camera channels (camera 1 animates its field of view: every
  segment holds the shot's): outside over Medtronic Plaza on the prow and the glass, a crane at midfield rising toward
  the west board, a pan from the north upper deck under the ETFE, a dolly along the south club level, and a push-in
  from the south-east over the blocks.
- **The field**: when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Vikings' 2026 end
  zones over clean turf (the retail s15 field shares each end-zone texture between the two ends); the turf and the
  apron on the Modern playing surfaces palette for s15 (that option's own painter and fit: the synthetic look, the
  2026 broadcast measured at U.S. Bank Stadium, the dome light; never tuned here); and a new midfield quad in the field
  scene carrying the folder's Vikings head. The field keeps the retail scratch word. Modern playing surfaces, run after
  this option, leaves the field's paint as it is and adds its detail normal.
- **The s15 row**: U.S. Bank Stadium, Minneapolis, MN, capacity 66,202; the indoor word stays 1 (the fixed roof: no
  rain or snow); the turf word and the flat climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s15 to it.

## Sources

- Facts: Wikipedia "U.S. Bank Stadium" (fetched 2026-09-27); the stadium's fact and media guide; vikings.com
  (2016-07-22: 205 ft at the east rising to 272 ft at the prow; the ridge truss and the queen's post trusses); the
  Thornton Tomasetti and Kawneer project pages; Daktronics (the boards).
- Plan: OpenStreetMap way 743461508 and its neighbours (ODbL 1.0), in `data/nfl2k5_usbank_model/footprint.json`.
- Photos: Wikimedia Commons (interiors 2016 to 2023 with two camera poses solved from the field lines, the 2018
  aerials, the plaza and the prow) and the Vikings' 2026 galleries (reference only).
- Art: `tools/nfl2k5_usbank_model_art.py`, deterministic; the U.S. Bank Stadium wordmark and the 3M and Land O'Lakes
  marks are cut from their Wikimedia Commons public-domain files (never redrawn); plain type otherwise; no players.

## Edition pack

`tools/nfl2k5_usbank_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

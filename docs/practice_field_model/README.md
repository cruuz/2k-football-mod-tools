# Modern practice facility (experimental)

Build option `modern_practice_field`, off in every preset. It writes a modern outdoor NFL practice facility into the
practice field, venue record s32 (retail "The Practice Facility", a college-style bowl), all nine bundles (day,
afternoon and night; dry, rain and snow). The game loads s32 for main-menu Practice (Scrimmage and Basic Training),
franchise Free Practice and MyCareer practice; nothing else loads it. The s32 row is not written.

The facility is a composite, neutral for all 32 teams (the venue is shared), built from cited references: Wikimedia
Commons photos of the Ravens', Seahawks', Bears', Dolphins', Eagles', 49ers' and Chargers' facilities and camps,
Wikipedia's articles on the Vikings', Seahawks', Bears' and Steelers' facilities, and OpenStreetMap plans of nine
facilities (read for dimensions only; no map data ships).

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the game's field in the middle framed by walkways; two more practice fields beside it (natural grass on the home
  side, synthetic on the away side) with their lines, hash marks, numbers and yellow single-post goalposts; the indoor
  field house behind one end (white ribbed metal walls, a clerestory lit at night, roll-up doors, a barrel roof); the
  team headquarters behind the other (a three-storey glass front, a taller entrance bay, a canopy); windscreen fences,
  six LED light poles, three filming towers (scissor lifts), training-camp bleachers with the game's crowd, a
  pavilion, a practice video board on the game's live feed (a crop at the board's aspect, never stretched), two
  practice clocks carrying the game's digits, sleds, dummies, JUGS machines and tents; outside, lawns, parking, a
  road, tree lines and the horizon drawn with the retail cityscape's own textures of the same bundle (the user's game
  data). The cityscape chunk is collapsed. The sideline props, pylons, yard markers and digits stay from retail. The
  side fields and lawns are baked to job tf's day targets (texture x baked vertex light). The scene fits the retail
  stored span of every bundle and decodes smaller than retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s32's own camera channels (each wants 0 where its camera carries no
  component): an aerial from behind the headquarters, field level behind an end zone, a filming tower's pan across the
  main field, a glide along the field house, and field 2's sideline.
- **The field**: the retail field's layout kept, plain grass end zones, the conference shields and the playoff mark
  cleared, Modern colour's grade when that option is on, then job tf's natural-grass surface (Kentucky bluegrass,
  tf's painter with its detail normal and divots), so the field reads applied under Modern playing surfaces' own
  signature. At midfield: the current NFL shield on a square quad when the 2026 venue art folder (the Build's
  `modern_venues_2026`) carries the league marks; league marks never ship, so without that folder the midfield keeps
  the game's own mark and quad.

Modern playing surfaces (`modern_surfaces`) writes the 288 home-venue bundles only, so it leaves s32 to this option.
The side-field and lawn greens follow tf's targets at build time; after tf changes its targets, re-record the pins
(`python3 -m mod_editor.core.nfl2k5_practice_field_model record-pins SOURCE`).

## Sources

- Photos: Wikimedia Commons (listed with their licences in the pf report, `PF_PRACTICE_FIELD_2026-09-27.md`),
  reference only.
- Plans: OpenStreetMap (ODbL 1.0), read for field spacing and building sizes only.
- Art: `tools/nfl2k5_practice_field_model_art.py`, deterministic; plain type only, no logos or players.

## Edition pack

`tools/nfl2k5_practice_field_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on
the model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

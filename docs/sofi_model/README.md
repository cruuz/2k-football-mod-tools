# SoFi Stadium (experimental)

Build option `modern_sofi`, off in every preset. It writes SoFi Stadium into the two venue records that share it: the
Rams (s23, retail Edward Jones Dome) and the Chargers (s24, retail QUALCOMM Stadium), all nine bundles each (day,
afternoon and night; dry, rain and snow).

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the bowl 30.5 m (100 ft) below grade in SoFi's tier stack (the official level maps), the translucent canopy on
  the OpenStreetMap outline with its aluminium edge and 37 columns, the Infinity Screen (a 110 x 59 m ring, 120 ft
  above the field) with the game's live feed in 16:9 windows and team panels, LED ribbons, the plaza, Rivers Lake,
  the neighbours and a sky backdrop. The sideline props, pylons, yard markers, banners and digits stay from retail.
  The scene fits the retail stored span of every bundle; nothing on the disc moves.
- **The intro cameras**: a new flyover per record, in an order where any three in a row (the pregame plays three from
  a varying start) show the whole Infinity Screen and an exterior pass: the press-box view from above the west 400
  level, a field-level crane in the north end zone, the lake aerial, the whole ring from the south upper deck and the
  east colonnade. Each shot wants 0 where its camera carries no component (the game plays those as 0).
- **The look pass (Noah's reference, 2026-09-24)**: the Infinity Screen's panels between the live windows are bright
  team content: for the Rams royal with three featured players (Stafford 9, Nacua 12, Williams 23), for the Chargers
  powder blue (Herbert 10, McConkey 15, Mack 52), each with his number, name and the club mark, tiled at the art's own
  8:1 aspect. The official 2026 portraits (nflverse-data roster_2026.csv headshot_url, the NFL.com images u1's league
  project uses) stay private: the art tool writes the portrait panels to the gitignored hydration folder
  `mod_editor/assets/nfl2k5_sofi_model/`, and a build uses them only when present and pinned (pins.json
  `portrait_art`, `model_portrait_sha256`); otherwise the committed panels without portraits;
  the Super Bowl panels carry the LXI mark and the NFL shield. The roof underside shows the white steel lattice; lit
  LED light banks (10 x 3 m, 30 degrees down) ring the canopy's rim; the fascia ribbons are team colour on every
  level; SoFi Stadium signs face the field at both ends below the middle deck.
- **The finish pass (after lab 4, 2026-09-24; c082, c105, c107)**: aisles cut every crowd band (1.2 m gaps, sections
  of 11.5 to 18 m, three to a corner, symmetric about the 50 and both end zones) over the seat texture's steps, which
  now sit at u = 0 of every section; the seating surface is sampled every four rows, which pays for the cuts; empty
  seats read as rows (pale riser edges); the suite glass is uniform dark glass under a white slab edge with a fine row
  of warm downlights; the walls under the overhangs and the rim's back wall show the shaded concourse behind a glass
  rail (`LIGHT_sf_concourse`), and the soffits sit in shade; the roof's top shows pale ETFE panels with dark joints
  and the operable louvres, as the aerials do. Every bundle stays at or under its retail decoded size.
- **The exterior (after lab 5, 2026-09-25; c103, c109)**: the bowl's outside reads as open concourses (lit white slab
  edges, fixtures, people, fine X-bracing); at night the soffit glows in team colour, the canopy's edge is a lit band
  under the SoFi Stadium letters, the columns and the ring are floodlit white and shaded by their normals (round and
  tapered), the plaza is lit and the sky is Los Angeles' overcast lit by the city. No geometry changes.
- **The field-level cloths**: the kept banner_corp takes job u4's reviewed 2026 league sheet (st's method for
  Highmark), carried to rain and snow from the dry bundle; the option cedes s23, s24 and s40 from the 2026 venue art, so
  the retail SEGA cloth showed behind the bench before (lab 6).
- **The field**: both teams' 2026 end zones and midfield (the photos are cited in `tools/nfl2k5_sofi_model_art.py`),
  the two ends in one panel set, and a dry field in every weather under the roof. One turf for both records: the
  Chargers' field lays the dome turf, surround, crisp white numbers and detail normal map of the Rams' record. The
  turf is composed before the Modern colour grade when that option is on; the painted marks keep their authored
  palettes after it (the grade's end-zone pass would move the Rams' sol toward lemon), so the official colours are
  exact.
- **The two stadium rows** (`nfl2k5_sofi_venue.py`): the name "SoFi Stadium, Inglewood, CA", the capacity 70,240,
  the roof (the indoor word, so no rain or snow falls on the field) and turf; one climate for both records.
- **The crowd**: the Rams and Chargers superfans in their 2026 colours (`nfl2k5_sofi_crowd.py`), on the user's own
  pixels.

The 2026 venue art option leaves s23 and s24 to this option. The 2K5 Edition pack for the model's 4x masters is
made with `tools/nfl2k5_sofi_model_pack.py` and x2's `tools/nfl2k5_texture_pack.py build` against the played disc's
catalog.

## Status

EXPERIMENTAL and UNWITNESSED: the lab runs are the job u6 report's; nothing here claims that anyone has seen it in
play.

## Super Bowl LXI (row s40)

The executable picks a franchise's Super Bowl venue by the season index; the first season plays in row s40 (retail
"Super Bowl 2005", Jacksonville). Super Bowl LXI is at SoFi Stadium on 2027-02-14, so with the option on the s40 row
reads "Super Bowl LXI" with "SoFi Stadium" as its display name, Inglewood, CA, roofed, on turf and with SoFi's
climate, and its nine bundles carry the same model: the LXI mark at midfield and on the screen and ribbons, the current
NFL shield on both 25-yard lines, one intro camera (the aerial over Rivers Lake). The executable's venue codes are
untouched.

The LXI mark is the NFL's own reveal image as @NFL posted it on X on 2026-02-09
(https://x.com/NFL/status/2020916447971623233), republished by SportsLogos.net credited to @NFL
(https://content.sportslogos.net/news/2026/02/IMG_9139-1000x562.jpeg): cropped to the primary mark and its black
background keyed, never redrawn, traced or generated (`tools/nfl2k5_sofi_model_art.py`, `super_bowl_mark`). It is sharp
at native size only, so the textures that carry it stay out of the 2K5 Edition 4x pack.

# Modern MetLife Stadium (experimental)

Beta 76 (job u2). Option `modern_metlife` (Build tab, "Modern MetLife Stadium (experimental)"), off in every preset,
needs a disc image. Owner `mod_editor/core/nfl2k5_modern_metlife.py`; rules and art `data/nfl2k5_modern_metlife/`
(`rules.json`, `art/`, `pins.json`); art generator `tools/nfl2k5_modern_metlife_art.py`; tests
`tests/mod_editor/test_nfl2k5_modern_metlife.py`. EXPERIMENTAL; see the job report for what was seen in a lab game.

## What the retail game has

The Giants and the Jets shared Giants Stadium in 2004, and the game carries two venue records for it: `s18`
"Giants Stadium" for Giants home games and `s19` "Jets Stadium" for Jets home games. Each record has nine archive
bundles, `s18{d,a,n}{d,r,s}.iff` (day, afternoon, night; dry, rain, snow). A bundle holds the field scene, the
stadium scene (85 shapes, 45 or 46 embedded P8 textures), the cityscape, the flyover camera records
(`intro_cameras`) and the skies. The two records share most of the geometry (64 of 85 stadium shapes are identical;
the field-level walls, signs and lower-bowl fronts differ) and differ in the team art (blue or green wall pads, the fan
banners, the end zones). MetLife Stadium was built beside the old stadium with a similar three-tier
bowl, so this option keeps the Giants Stadium bowl, removes the pieces MetLife does not have (the rooftop
press box and the light towers) and reworks everything drawn on the rest.

## What it changes

| Piece | How | Giants (s18) | Jets (s19) |
| --- | --- | --- | --- |
| seats (`seat01/02/03`) | palette rule, retail indices kept | charcoal grey | charcoal grey |
| steel, soffits, frames (`roof01`, `lite02`), structure (`cement01`) | palette rule | neutral silver | neutral silver |
| suites and club glass (`suite01..04` and the lit night versions) | palette rule | cool tinted glass | cool tinted glass |
| field-level wall pads (`wall01`; Jets also `wall04`) | authored patch | royal blue, NEW YORK / GIANTS, red base band | Legacy green, NEW YORK (logo) JETS, white stripes; the round sign becomes the 2024 logo |
| LED fascia ribbons (`banner01/02/04`) | authored patch | GIANTS, ny, GO BIG BLUE, MetLife, sponsors | JETS, logo, GANG GREEN, MetLife, sponsors |
| end-zone video boards (`ad_bb01/02` and the lit night copies) | authored patch (field-level panels stay retail) | METLIFE STADIUM, ny, GIANTS, MetLife, GO BIG BLUE | METLIFE STADIUM, logo, JETS, MetLife, J-E-T-S! |
| field sponsor banners (`banner_corp`), fan banners | authored patch on the retail cloth | MetLife, NFL, sponsors, team marks; u1's Giants fan banners | same set in green; J-E-T-S!, GANG GREEN, TAKE FLIGHT |
| end zones (`endzone_N/S_L/M/R`) | opaque overlay (b76-u5b: the old 8% see-through let the retail wordmark show as an offset ghost, a false drop shadow) | royal blue, the 1976 GIANTS wordmark with its underline and the ny at each side, every mark edged in dark navy, laid out from the Giants' 2024-08-08 photo (b76-u5b) | green; seen from the field, the plane roundel (the 2024 oval with the plane alone) then JETS in the 2024 letters without the plane, placed from the rectified 2026-09-20 White Out photo (b76-u5b) |
| midfield (`center_logo`) | replaces the retail NFL shield | the 2024-present helmet (white ny, red stripe along the shell top, grey facemask) at its painted size, about 16 yards along and 14.6 across: the quad's four corners move out (b76-u5b; measured through a homography fitted on the yard lines, the hash rows through the marks' centres at 10 ft 3 in, and the sidelines) | the 2024 Jets logo reversed (white oval, green ring and letters), 14.8 x 8.85 yards, its own 1.67:1 oval |
| venue name (main ROST, stadium records s18/s19) | repacked string block | MetLife Stadium | MetLife Stadium |
| west rooftop press box with its two lamp banks (`group41`, `group43`, `group44`) | collapsed | gone | gone |
| four corner light towers (`group40`, `group42`, `group45`, `group50`), two east lamp banks (`group47`, `s19_8`) | collapsed | gone | gone |
| the fourteen light-glow and four lens-flare markers (`marker_lightShape1..14`, `marker_flare*`) | moved | onto the roof rim, same bearings | onto the roof rim, same bearings |

Rain and snow: every patch and overlay takes the look of the user's own retail variant pair (a per-channel affine
fit of retail dry to retail rain or snow over the patched region, each channel's gain pulled toward the joint gain
of the three channels where the retail art barely varies in it; the wall pads also take the retail snow drifts).
Untouched: the rest of the geometry (the bowl, the suites, the end-zone boards, the flagpoles on the east rim),
the other scene markers (players, coaches, cameras, the jumbotron), the crowd scenes (`crowds18`, `crowds19`), the grass colour map and bump map (Modern colour owns
them), the yard markers (`yardfront`, `yardside` are the orange sideline yard-number boxes), the sideline props,
the scoreboard digits, the cityscape and the flyover camera paths.

## Geometry: collapse, not move

Every retail shape carries a tight bounding sphere (shape +0x00 centre, +0x48 radius) that the frustum test
reads, and lowering the towers or the press box onto the rim puts vertices outside it. A collapse moves every
vertex of the shape to the sphere centre instead: the vertex count, topology, materials, streams and the sphere
stay retail, every triangle has zero area, and every vertex is inside the sphere. The nine shapes own their
FLOAT3 position streams (no other shape reads those bytes), and the test checks that the stadium scene's system
bytes change only in those position lanes and the eighteen marker positions.

The executable registers a light glow at every stadium marker whose name holds "light" and a lens flare at every
one whose name holds "flare" (0x0007F210, position at marker +0x10; the flare is drawn by 0x0007EC40 with an
intensity that falls off with its distance from the screen centre); 0x00097B80 also copies the four
`marker_flare` positions as the player-shadow lights of shadow mode 2 (0x0009A390). All eighteen sat on the lamps;
each moves onto the roof rim on its own bearing (1.5 m above the rim top, 2 m inside the rim's outer edge), so
glows and flares come from the ring where MetLife's lights are, not from the air where a tower was. The shadow
lights keep their bearings and drop from 67 to 82 m to 59.8 m (longer shadows, same directions). A marker moves
only from its pinned retail bytes.

## Fixed allocation

Every scene is refit inside its retail VC-LZ span and the whole 32-byte wrapper, the loader scratch word included,
stays retail. The stadium scenes compress well below their span with the new art; what they needed was the
in-place decode constraint, which peaks near the end of the stream, so the writer fills the stream to the last byte
of the stored body (padding 0) before measuring it. All eighteen bundles fit with the authored textures at 256
palette entries; a scene that did not would be repainted with fewer entries for the authored textures only (128
down to 32) before the option refuses. `record-pins` recompiles all eighteen bundles from a retail source in
about 50 seconds; the build does the same in parallel, and with Modern colour on it composes the field art into
the colour option's field refit, also in parallel.

## Venue name

The stadium record in the main ROST points at five strings: +0x00 name, +0x08 location, +0x0C asset code, +0x10
display name, +0x14 crowd code. The asset code is the engine's file-name key (`%s%c%c.iff`); every stadium search
in the executable compares it and nothing else (FUN_000BFB60 for historic teams, FUN_001332B0 and FUN_00133370,
FUN_002C0C20 in the stadium menu), and the names exist only in the ROST resources. The option repacks the two
records' string blocks so name and display name share one "MetLife Stadium" allocation, keeps the location and the
asset code, zero-fills the rest of the retail block and rewrites the ten pointers.

## Proof

`python3 -m mod_editor.core.nfl2k5_modern_metlife record-pins <packs>` compiles every bundle and the ROST from the
retail packs; the test re-derives the Jets night-rain bundle against its pin, checks the retail wrappers and the
untouched bytes, checks that the Giants day stadium changes only the collapsed position lanes and the eighteen
moved markers outside its textures (spheres retail, every other shape's positions retail), and checks the ROST rename.
`status` reports retail / applied / mixed / foreign.

Review images are retained in private development evidence.
Review images are retained in private development evidence.

The images above are offline Blender renders of the decoded scenes (flat lit, crowd hidden), not game frames.

# Modern playing surfaces (experimental)

Build option `modern_surfaces`, module `mod_editor/core/nfl2k5_modern_surfaces.py`, off in every preset. Written
2026-09-25, revised 2026-09-27 (tf-v2) after the first lab frames. Labels: PROVED IN GAME (seen in a lab frame),
PROVED OFFLINE (tests, byte read-back, offline renders), DESIGN (a choice), INFERRED (read from evidence, not proven).

## What it does

Every team's home field gets the surface its 2026 stadium really has (`data/nfl2k5_modern_surfaces/venues.json`, one
row per venue record with public sources):

- **Synthetic turf** (16 records: ATL, CAR, CIN, DAL, DET, IND, MIN, NE, NO, NYG, NYJ, LAR, LAC, SEA, TEN, HOU). The
  saturated, even green of today's FieldTurf and Hellas fields on broadcasts, the factory two-tone 5-yard bands, and a
  detail normal of fine fibres lying every way with dark infill between the tufts, instead of the retail white noise.
- **Natural grass** (16 records: ARI, BAL, BUF, CHI, DEN, GB, JAX, KC, MIA, LV, PHI, PIT, SF, TB, WAS, CLE). Brighter and
  healthier than retail, mown in 5-yard stripes (or a checkerboard look), with a fine-blade detail normal.

The venues that swapped their turf for grass for the 2026 World Cup (MetLife, SoFi, Gillette, AT&T, NRG/Reliant,
Mercedes-Benz, Lumen) went back to synthetic turf for the NFL season; the table cites each return. Teams that moved
keep their 2004 building in the game, and the surface follows the 2026 venue (for example LV: the Oakland model with
Allegiant's Bermuda grass).

The ROST turf word (+0x1C) is never written. It changes wear, divots, night shadows, uniform stains and two gameplay
scalars, so a flip is a gameplay decision. On synthetic venues that keep the retail grass word, this option makes the
divots invisible (palette alpha 0) and turns the Fldd wear colour (word 1) from brown dirt into dark scuffed turf.

## How the game draws a field (PROVED OFFLINE)

| Piece | Where | Fact |
| --- | --- | --- |
| Colour map | field SCNE, `color_premipped` 128 x 64 P8, 4 mips | Grass venues: a 1,499-vertex grid (2.29 m cells) with UVs at 45 degrees, mirrored per cell, 5 cm per texel. Turf venues: one quad from goal line to goal line (u 0.5 to 1). s02, s06, s09 and s26 have no colour texture (a material colour word). |
| UV decode | shape record +0x30: 4 floats | NORMSHORT2 UV x (scale u, scale v) + (offset u, offset v); retail (0.501, 0.501, 0.5, 0.5) for the field shapes. |
| Detail layer | detail_layer SCNE, shape `E_detail` (2,429 vertices) | The same diagonal, mirrored mapping; the material `detail` gets `specularmap`, `detail_normal` and `shadow` (0x9C2FA..0x9C3A9, blend word 0x302). |
| Detail normal | TXTR `detail_normal` 512 x 256 P8, 6 mips | A RAW chunk of 175,872 bytes in 30 venues (any content fits); a compressed chunk in s11 and s15. 1.27 cm per texel. Retail: white noise, mean tilt 40 to 53 degrees. |
| Divots | TXTR `divots` 64 x 64 P8 | Only in venues whose ROST word says grass. |
| Fldd | words 0..4 | Word 1 the wear dirt colour (0xE05E5430), word 2 the time-of-day tint the field multiplies by. |

A field's stored span is a fixed VC-LZ allocation (most retail streams leave a few bytes). Per-texel colour noise does
not fit; bands and a smooth mottle do (5 to 19 KB of room on the greedy encoder). The detail normal, a raw chunk, is
where the fine texture lives.

## What the option writes (DESIGN, PROVED OFFLINE)

- Grid fields (1,499 vertices): the colour submesh's UVs become one planar mapping, one period = 10 yards along and
  10 yards across (7.1 cm per texel along the field), under the UV constant (32767/4096, 32767/4096, 5, 3) so the
  grid's 2.286 m steps land on multiples of 1,024 and the vertex stream stays compressible. The grid wraps: its bands
  show in game (PROVED IN GAME at Arrowhead, about 3 percent).
- Quad fields (one quad goal line to goal line: the retail turf venues, among them MetLife, Lumen, SoFi's s23,
  Highmark and Lucas Oil): the game samples them clamped (PROVED IN GAME, candidate B: one light band at the goal
  line where u = 0 and the edge texel's tone past u = 1, no bands elsewhere; the offline render with a clamped sampler
  matches the frame). tf-v2 maps the WHOLE field inside 0..1: 20 bands of 5 yards along (6 texels each on 128) between
  1/32 margins, under the UV constant (32767/65536, 32767/65536, 0.5, 0.5).
- Every end-zone vertex of the colour shape is re-encoded under the new constant, so its UV does not move (tests:
  within 1/2048).
- The colour map: the look's pattern (bands or checker, smooth mottle) around a mean solved per bundle so that
  map x rig gain x Modern colour's screen factor x the Fldd tint x the grass vertex tint x the game's measured
  response lands on the broadcast target for that bundle's light (day, afternoon, night, dome, rain, snow). The target
  is the look's, or the venue's own measured 2026 broadcast (`broadcast` in the venue table: 16 records, its ratio to
  the look carried to the venue's other lights; a row may also carry a `design` target of the same shape that replaces
  the measurement, as Allegiant's does since Beta 77 pass 4: the dome grass re-aimed from the broadcast (86, 114, 58) to
  (75, 106, 49), about 9 percent darker and 3 degrees cooler, halfway to the 2026 Week 1 photos). The rig is the retail one, or Modern colour's configured rig from its
  receipt. Channels are clamped so the map stays a plausible green (red and blue never pass green), and the whole map
  scales down if a channel would pass 238.
- Fields drawn from a material colour (s02, s06, s09, s26): the colour material borrows the outside-grass texture
  record (its texture pointer) and the outside grass keeps a plain matching colour.
- The outside grass (the apron) draws 0.93 of the field target in the field's own chroma, through the apron response
  measured in game (it is not under the detail layer).
- End zones painted over the old turf: palette entries inside the old turf's colour envelope (hue +-12 degrees,
  saturation and value +-0.10) take the new turf colour with their shading; team paint is untouched (tests: sol gold,
  dark greens, white, navy, midnight green).
- The detail texture (tf-v3): the look's kind (`fibre`, `helix`, `blade_bermuda`, `blade_bluegrass`) from the shipped
  palette PNG. The game shows this texture through its palette ALPHA (see the measured response), so the 256 entries
  carry one flat normal and alpha = the index, and the pixels carry short blades or fibres (2 to 3.5 texels, 2.5 to
  4.5 cm) with dark gaps (infill specks on synthetic turf). Every mip level keeps the mean alpha the colours were
  measured with (163 fibre, 168 helix, 143 the blades) and its spread falls with distance: standard deviation / mean
  0.075 to 0.080 at mip 0 and 0.045 to 0.053 at mip 1 (the coin toss and replays; tf-v3.1, a third of tf-v3's after
  lab 5 and candidate C showed twice the predicted grain up close and painted logos reading as gravel from the
  overhead coin-toss camera), then 0.032 to 0.050 at mip 2, 0.017 to 0.028 at mip 3 and 0.005 to 0.007 at mip 5
  (the play camera, unchanged: 0.015 to 0.022 in lab 5). Nothing is longer
  than a texel or two, because the game maps the texture per triangle with discontinuous UVs (592 of the 618 shared
  positions of E_detail), so longer structure shows the triangle lattice (PROVED OFFLINE on the game's own UVs).
- The compressed chunks of s11 and s15 take three tileable 64 x 64 tiles laid in an irregular grid (`TILE_GRID`) that
  repeats every third 64 x 64 block in the texture's swizzled order (inside the 14-bit match distance); one repeated
  tile showed a lattice.
- Fit ladder per field: (pattern detail 2, 256 colours), (2, 64), (1, 64), (1, 32), (0, 32), the greedy encoder over
  the whole ladder first and the optimal parser only if none fits. The retail 32-byte wrapper, loader scratch word
  included, never changes.

Build step: last of the stadium writers (after Modern colour, Arrowhead, MetLife and its model, the 2026 venue art,
SoFi and Highmark). It repaints what they left, updates Modern colour's receipt (bundle pins, the MetLife and
Arrowhead rows) and the 2026 venue receipt, and writes `<image>.surfaces.json`. The painter is idempotent, so a
writer may compose it itself and the post-pass then leaves the same bytes.

## The game's measured response (PROVED IN GAME, tf-v2)

Candidate B (tf-v1) was read in eight lab runs (tf lab 3 and ig's smoke lab, stock xemu at 1x, 2026-09-27): the median
turf of each run's play frames against the offline model of the same disc's bundle (clamped colour map on quads).

| Run | Layout, detail | Game | Model | Game / model |
| --- | --- | --- | --- | --- |
| Arrowhead day | grid, blades | (99,118,63) | (91,109,63) | 1.09, 1.08, 1.00 |
| Arrowhead night | grid, blades | (107,118,52) | (105,116,54) | 1.02, 1.02, 0.96 |
| Highmark day | quad, blades | (92,117,60) | (80,100,58) | 1.15, 1.17, 1.03 |
| Highmark night | quad, blades | (95,115,57) | (88,104,53) | 1.08, 1.11, 1.08 |
| MetLife day | quad, fibre | (108,133,73) | (80,98,58) | 1.35, 1.36, 1.26 |
| MetLife night | quad, fibre | (87,110,72) | (70,87,57) | 1.24, 1.26, 1.26 |
| Lumen night | quad, fibre | (87,109,71) | (70,87,57) | 1.24, 1.25, 1.25 |
| SoFi (Rams), dome | quad, helix | (112,138,74) | (84,104,55) | 1.33, 1.33, 1.36 |

- Modern colour's own fields (retail detail normal) match the same model within 5 percent (MetLife day and night,
  Lambeau). The excess follows this option's detail normal (palette alpha 0.64 fibre, 0.66 helix, 0.56 the blades;
  INFERRED as the cause) and the layout (a quad draws 1.07 x a grid). `FIELD_RESPONSE` holds the grid values per
  detail kind and light, `QUAD_RESPONSE` the quad factor; afternoon, dome and rain or snow values are INFERRED.
- The apron draws about twice the field model per unit of map and nearly neutral: in-game apron / (map x rig gain x
  screen factor x Fldd tint x vertex tint) = 1.98 to 2.19 by day, 1.88 to 2.09 at night, 1.97 to 2.11 under SoFi's
  dome (`APRON_RESPONSE`). Modern colour's `OUTSIDE_RESPONSE` (1.17, 1.41, 1.49, one retail sample) under-weights red,
  so tf-v1's aprons drew lime: (140,150,77) beside a (107,133,73) field at MetLife by day, (142,151,84) at Arrowhead.
- The synthetic fields drew 16 to 36 percent brighter than their targets: MetLife night (87,110,72) against the SNF
  broadcast (71,91,61). Arrowhead at night drew (107,118,52) against the MNF broadcast (106,120,53).
- Detail (tf-v1 and v2): no fibre or blade texture showed in game at any camera, the coin toss and replays included
  (grain 0.002 to 0.009), while the retail detail drew 0.024 to 0.11. The game's mip choice follows the GPU's isotropic
  rule at 640 x 480 (the play camera samples mips 1.4 to 5 and more, the coin toss 0 to 2, a replay close to the turf
  mip 0), so tf-v1's normals were sampled where they had tilt; they simply do not show. The alpha does: the retail
  map's alpha varies (standard deviation / mean 0.45 at mip 0), tf-v1's did not (one value). An alpha model fitted to
  the retail labs (the modulation = 1 + 0.6 x (alpha / level mean - 1)) reproduces the retail grain at the coin toss
  and from above, and tf-v1's flat look.

## Status and receipts

- The build step writes `<disc>.surfaces.json` and the build publishes it beside the disc, like the Modern colour and
  2026 venue receipts. Lab 1 (2026-09-25) failed its status gate because the publish step did not carry it yet
  (fixed in 5083c3129).
- `python3 -m mod_editor.core.nfl2k5_modern_surfaces status DISC [--deep] [--report FILE]` prints, per bundle, the
  counts by state and reason and every bundle that is not applied; the state is the last line. A bundle is applied
  when it matches the receipt, or when it still carries this option's detail normal (no receipt row, or another
  writer changed other chunks after this step: end zones, logos, the stadium). `--deep` also decodes each field and
  requires the planar colour UVs, so a field rebuilt from retail reads foreign.

## References (cited; nothing here ships)

Surfaces: the Wikipedia list of current NFL stadiums (raw wikitext, 2026-09-25), FieldTurf's 2025 NFL list (eight
teams on FieldTurf CORE), Hellas Construction (Matrix Helix at SoFi, AT&T, NRG, Nissan, Lucas Oil), the Vikings (Act
Global Xtreme Turf DX, 2024), and the 2026 post-World Cup reports per venue. Every row of `venues.json` carries its
URLs.

Materials: FieldTurf CORE is a multi-layer, dual-polymer monofilament fibre ("a more realistic, textured, grass-like
shape"); Matrix Helix uses spiral monofilament fibres, olive and sports green yarns stitched on alternate needles, a
2 to 2.25 in pile, SBR, cellulose or organic infill (Nissan Stadium: organic). Synthetic fields are laid in 15 ft rolls,
which is why their tone bands are 5 yards wide.

Broadcast colour (2026 Week 1 highlight uploads and three ESPN games; the Modern colour mask: hue 60 to 160, saturation
over 0.30, value 0.20 to 0.95; median of per-frame medians):

| Game | Venue | Surface | Light | Turf RGB | HSV |
| --- | --- | --- | --- | --- | --- |
| NE at SEA | Lumen Field | synthetic | late afternoon | (86, 106, 69) | 92, 0.35, 0.42 |
| NYJ at TEN | Nissan Stadium | synthetic | day | (86, 105, 55) | 83, 0.48, 0.41 |
| TB at CIN | Paycor Stadium | synthetic | day | (90, 108, 68) | 87, 0.37, 0.43 |
| CHI at CAR | Bank of America Stadium | synthetic | day, overcast | (57, 76, 49) | 102, 0.36, 0.30 |
| BAL at IND | Lucas Oil Stadium | synthetic | dome | (102, 125, 78) | 90, 0.37, 0.49 |
| BUF at HOU | Reliant (NRG) Stadium | synthetic | dome | (100, 130, 65) | 88, 0.50, 0.51 |
| NO at DET | Ford Field | synthetic | dome | (63, 85, 58) | 109, 0.32, 0.33 |
| GB at MIN | U.S. Bank Stadium | synthetic | dome | (105, 118, 73) | 77, 0.38, 0.46 |
| ARI at LAC | SoFi Stadium | synthetic | canopy | (101, 119, 75) | 85, 0.37, 0.47 |
| DAL at NYG (SNF clip) | MetLife Stadium | synthetic | night | (71, 91, 61) | 100, 0.33, 0.36 |
| ATL at PIT | Acrisure Stadium | grass | day | (94, 106, 71) | 81, 0.33, 0.42 |
| CLE at JAX | EverBank Stadium | grass | day | (106, 128, 75) | 85, 0.42, 0.50 |
| WAS at PHI | Lincoln Financial Field | grass | late afternoon | (110, 132, 76) | 83, 0.42, 0.52 |
| MIA at LV | Allegiant Stadium | grass | translucent roof | (86, 114, 58) | 90, 0.49, 0.45 |
| DEN at KC (MNF, 223 frames) | Arrowhead Stadium | grass | night | (106, 120, 53) | 73, 0.56, 0.47 |
| SEA at SF (2026-01-03) | Levi's Stadium | grass (winter) | night | (106, 113, 44) | 66, 0.61, 0.44 |
| CAR at TB (2026-01-03) | Raymond James Stadium | grass (winter) | late afternoon | (93, 111, 49) | 77, 0.56, 0.44 |
| HOU at PIT (2026-01-12) | Acrisure Stadium | grass (winter) | night | (102, 105, 52) | 63, 0.50, 0.41 |

Texture on broadcasts: synthetic fields show crisp two-tone 5-yard bands (the band contrast on wide shots: about 5 to
20 percent in luminance) and, up close, a fine fibrous grain; grass shows softer mowing stripes and looks smooth at
broadcast zoom. September grass is yellow-green (hue 72 to 90); January grass goes yellower (hue 63 to 77) and is not
the target.

## Looks (DESIGN; the owner picks)

| Look | Family | Detail | Bands | Day target |
| --- | --- | --- | --- | --- |
| `synthetic_fieldturf` | synthetic | fibre | +-7 %, 5 yd | (88, 108, 64) |
| `synthetic_helix` | synthetic | helix | +-9.5 % | (86, 107, 58) |
| `synthetic_vivid` | synthetic | fibre | +-6 % | (84, 114, 56) |
| `grass_bluegrass` | grass | blade_bluegrass | +-5 % stripes | (88, 110, 64) |
| `grass_bermuda` | grass | blade_bermuda | +-6 % stripes | (102, 121, 70) |
| `grass_checker` | grass | blade_bermuda | +-5 % checkerboard | (100, 120, 68) |

The table assigns FieldTurf, Act Global and Turf Nation venues `synthetic_fieldturf`, Hellas venues
`synthetic_helix`, bluegrass and hybrid venues `grass_bluegrass` and Bermuda venues `grass_bermuda`.

## Proof (PROVED OFFLINE)

- All 288 home-venue bundles (32 venues x 9), from the retail packs and again after Modern colour's default grade:
  288 of 288 fit their spans with the retail wrapper; 240 at full pattern detail and 256 colours, 48 snow bundles at
  pattern detail 1 and 64 colours, 18 compressed detail normals (s11, s15) with the tiled art; a second pass leaves
  every bundle byte-identical.
- Composition in the real final order, in memory, for all 288 home bundles: retail, then Modern colour, then the
  writer that owns the venue (252 through the 2026 venue art from the division jobs' art root, 18 through Modern
  MetLife's combined bundle, 18 through SoFi's field), then this option. All 288 fit; only this option's sites change;
  the midfield logo, numbers, shields, playoff mark and tarp keep their bytes (5 to 7 textures per field); the end zones
  keep their indices and their paint (20,151 turf-background palette entries in 81 bundles follow the new turf, each
  inside the old turf's colour envelope); the planar UVs are there; the deep status reads applied for every bundle.
  The league visual project (k2 v4, 5,838 edits) is applied before the build plan, and none of its edits targets a
  home bundle (its 557 p8 edits touch 120 outers, none of the 288).
- `tests/mod_editor/test_nfl2k5_modern_surfaces.py`: the table, the art, the colour solve, the end-zone recolour, a
  grid field (planar UVs, end zones unmoved, only the planned sites change, the wrapper kept), a borrowed-texture
  field, synthetic divots and wear, a compressed detail normal, the release catalog and the build wiring.
- Offline renders (a ray-cast of the real field scenes with trilinear mips and Modern colour's calibrated model,
  fitted to a lab frame at Lambeau by day): the candidates draw their broadcast targets; moving the game camera 4 cm
  changes the mid field by 0.0047 (synthetic) and 0.0036 (grass) of its mean, against 0.0133 retail and 0.0087 for
  Modern colour today, so the new detail shimmers less.

## Known limits

- tf-v2's colours are solved with the response measured on candidate B (tf-v1's art); a detail normal with another
  alpha needs the response measured again. The quad fields' whole-field mapping and the v2 colours are witnessed only
  when lab 4 reads out (tf/lab/tf_lab4.sh).
- tf-v3's blades are PREDICTED (offline, the alpha model): at the coin toss and replays a fine blade texture at 55
  to 60 percent of the retail texture's grain; at the play camera a little more grain than tf-v1 and far under
  retail; shimmer for a slow pan at the play camera 22 to 58 percent of retail's at 1x (35 to 69 percent at 2x).
- Lab 5 (PROVED IN GAME): the play camera 0.015 to 0.022 (as predicted); up close about twice the prediction
  (Arrowhead 0.043, Highmark 0.057; candidate C's overhead coin toss at MetLife 0.07 to 0.11 on the painted logo). The
  model's gain refit on those frames is 1.25 (the first fit, 0.6, used two retail labs). tf-v3.1 predicts the coin toss
  at 0.020 to 0.024 and the overhead logo at 0.008 to 0.028, the play camera unchanged.
- Quad bands use 6 texels per band on the 128-texel map, so far bands soften with the mips.
- The blue channel under the warm retail rigs is the model's weakest part; maps are clamped to stay green.
- A disc built with the MetLife skin alone and without Modern colour reads the skin as foreign after this option (its
  pins cannot learn the new field); with Modern colour or the MetLife model the receipts are updated.
- Rain and snow looks are extrapolated (no references). Snow bundles use the simpler pattern to fit.

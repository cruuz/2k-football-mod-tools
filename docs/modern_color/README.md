# Modern colour and lighting: 2026 Week 1 broadcast references and the game's levers

Written by Claude Fable 5.1 on 2026-09-15 for beta 70. EXPERIMENTAL / UNWITNESSED: every value below is measured from broadcast stills or decoded from the disc; nothing here is a claim about how the game looks after the option, which no one has watched yet.

## Reference material

- `Denver Broncos vs Kansas City Chiefs Game Highlights | 2026 NFL Season Week 1` (ESPN Monday Night Football, Arrowhead Stadium, 8:15 PM ET kickoff): 30,044 frames at 1920x1080, every 40th frame measured (752 frames). This is the anchor Noah named.
- `Best Play From EVERY Team In Week 1 | 2026 NFL Season` (NFL, 9:14, 554 frames at 1 fps, 31 scene cuts): one play per team; each game's frame range was assigned by hand from the scorebugs and end-zone art (contact sheets of all 554 frames).
- `Cam Skattebo FLIPPING Into The Endzone For His First TD` (NFL, 28 s, 55 frames at 2 fps): Cowboys at Giants, MetLife Stadium, Sunday Night Football.
- Schedule and kickoff times: nflschedules.com and nfl.com Week 1 pages (Wed 9/9 NE at SEA 8:20 PM ET; Thu 9/10 SF vs LAR at the MCG in Melbourne, 10:35 AM local; Sun 9/13 1:00 PM ET slate, 4:25 PM ET slate, 8:20 PM ET SNF; Mon 9/14 8:15 PM ET MNF).

Measurement method (`measure_week1_games.py` and `measure_frames.py` beside this file): per frame, the top 900 rows (above the scorebug band) subsampled 2x; turf = pixels with hue 60..160, saturation over 0.30, value 0.20..0.95; white = saturation under 0.12 and value over 0.85; skin = hue 8..35, saturation 0.25..0.65, value 0.35..0.90; uniform clusters = the two strongest 30-degree hue bins among saturated non-green pixels; top band = the median of the top 50 rows (crowd, sky or roof). Values are medians over the game's frames, RGB 0..255.

## Per-game table (all 32 teams)

| Game (away at home) | Stadium | Roof | Kickoff bucket | Frames | Turf | White | Skin | Top band | Uniform clusters (hue: RGB) |
|---|---|---|---|---|---|---|---|---|---|
| NE@SEA | Lumen Field, Seattle | open | late afternoon (8:20 ET = 5:20 PT, sun up) | 1-33 (33) | (86, 106, 69) | (215, 218, 223) | (127, 94, 79) | (91, 100, 86) | h210: (30, 39, 71); h330: (154, 24, 57) |
| SF@LAR | MCG, Melbourne | open | day (10:35 local) | 34-60 (27) | (69, 77, 49) | (216, 218, 223) | (145, 105, 85) | (76, 75, 62) | h210: (50, 58, 114); h30: (160, 125, 35) |
| NYJ@TEN | Nissan Stadium, Nashville | open | day (1 ET) | 61-96 (36) | (86, 105, 55) | (239, 237, 230) | (129, 93, 69) | (97, 112, 79) | h210: (73, 118, 177); h180: (87, 149, 206) |
| ATL@PIT | Acrisure Stadium, Pittsburgh | open | day (1 ET) | 97-136 (40) | (94, 106, 71) | (215, 218, 223) | (120, 88, 77) | (96, 107, 69) | h30: (137, 109, 28); h330: (149, 4, 45) |
| CLE@JAX | EverBank Stadium, Jacksonville | open | day (1 ET) | 137-176 (40) | (106, 128, 75) | (215, 218, 223) | (139, 101, 74) | (107, 120, 84) | h180: (15, 103, 117); h0: (232, 61, 36) |
| BAL@IND | Lucas Oil Stadium, Indianapolis | dome | dome (1 ET) | 177-218 (42) | (102, 125, 78) | (243, 243, 241) | (127, 98, 80) | (54, 55, 85) | h210: (34, 50, 103); h240: (41, 36, 82) |
| BUF@HOU | NRG Stadium, Houston | dome | dome (1 ET) | 219-253 (35) | (100, 130, 65) | (238, 232, 233) | (138, 101, 82) | (111, 140, 84) | h210: (34, 52, 129); h330: (183, 33, 53) |
| NO@DET | Ford Field, Detroit | dome | dome (1 ET) | 254-282 (29) | (63, 85, 58) | (228, 225, 239) | (129, 95, 80) | (72, 91, 105) | h210: (20, 84, 183); h180: (14, 119, 174) |
| TB@CIN | Paycor Stadium, Cincinnati | open | day (1 ET) | 283-317 (35) | (90, 108, 68) | (245, 238, 229) | (128, 89, 72) | (84, 92, 61) | h0: (184, 71, 45); h330: (167, 32, 52) |
| CHI@CAR | Bank of America Stadium, Charlotte | open | day (1 ET) | 318-352 (35) | (57, 76, 49) | (215, 218, 223) | (122, 86, 70) | (59, 79, 52) | h180: (40, 138, 183); h0: (178, 65, 32) |
| WAS@PHI | Lincoln Financial Field, Philadelphia | open | late afternoon (4:25 ET) | 353-386 (34) | (110, 132, 76) | (215, 218, 223) | (133, 98, 80) | (99, 110, 70) | h330: (100, 27, 55); h30: (212, 166, 41) |
| GB@MIN | U.S. Bank Stadium, Minneapolis | dome | dome (4:25 ET) | 387-433 (47) | (105, 118, 73) | (231, 221, 224) | (158, 113, 86) | (115, 127, 82) | h30: (205, 169, 48); h0: (170, 103, 79) |
| MIA@LV | Allegiant Stadium, Las Vegas | dome | dome (4:25 ET) | 434-464 (31) | (86, 114, 58) | (215, 218, 223) | (121, 88, 75) | (86, 93, 63) | h150: (14, 121, 109); h180: (2, 141, 148) |
| ARI@LAC | SoFi Stadium, Inglewood | dome (canopy) | dome-canopy (4:25 ET = 1:25 PT) | 465-495 (31) | (101, 119, 75) | (246, 241, 242) | (149, 106, 85) | (100, 123, 90) | h210: (73, 107, 176); h180: (26, 128, 199) |
| DAL@NYG | MetLife Stadium, East Rutherford | open | night (8:20 ET) | 496-517 (22) | n/a | (217, 218, 234) | (136, 99, 84) | (100, 100, 131) | h210: (36, 46, 101); h240: (47, 42, 97) |
| DEN@KC | Arrowhead Stadium, Kansas City | open | night (8:15 ET) | 518-554 (37) | (111, 125, 57) | (217, 218, 223) | (133, 92, 77) | (104, 77, 67) | h330: (138, 29, 51); h0: (132, 66, 50) |
| DAL@NYG (Skattebo clip, 2 fps) | MetLife Stadium | open | night (8:20 ET) | 1-55 (55) | (71, 91, 61) | (220, 218, 232) | (125, 94, 81) | (76, 59, 77) | h210: (43, 55, 121); h240: (49, 42, 96) |
| DEN@KC (full MNF highlight, every 40th frame) | Arrowhead Stadium | open | night (8:15 ET) | 1-30044 (752), step 40 | (107, 121, 53) | (231, 218, 213) | (137, 96, 76) | (106, 96, 55) | n/a |

Uniform cluster hues, for the record: 330-345 = red (Chiefs, Cardinals, Texans, Buccaneers, Falcons red); 0-30 = orange/brown (Browns, Bengals, Broncos orange, skin spill); 30-60 = gold/yellow (Steelers, Packers gold, Rams gold); 180 = teal (Jaguars, Dolphins, Panthers blue); 200-240 = blue/navy (Patriots, Seahawks, Cowboys, Giants, Bills, Colts, Lions, Chargers, Titans light blue, Vikings purple sits at 240-280).

## What the buckets say

| Bucket | Games | Turf median | Turf range | Notes |
|---|---|---|---|---|
| Day, open air (1 PM ET and the Melbourne morning) | SF at LAR (MCG), NYJ at TEN, ATL at PIT, CLE at JAX, TB at CIN, CHI at CAR | (88, 105, 61), HSV about 83 degrees, 0.42, 0.41 | (57, 76, 49) Charlotte overcast to (106, 128, 75) Jacksonville sun | Whites (215..245, 218..238, 223..230): neutral. Sun games carry hard shadows; overcast Charlotte and the shaded MCG are darker and greener. |
| Late afternoon, open air (4:25 PM ET, and Seattle's 5:20 PM local Wednesday) | WAS at PHI, NE at SEA | (98, 119, 72), HSV about 81 degrees, 0.39, 0.47 | (86, 106, 69) to (110, 132, 76) | Warm but not orange; whites stay neutral (215, 218, 223). |
| Night, open air (8:15 and 8:20 PM ET) | DEN at KC (Arrowhead, anchor), DAL at NYG (MetLife) | Arrowhead (107, 121, 53), HSV 73 degrees, 0.56, 0.47; MetLife (71, 91, 61), HSV 96 degrees, 0.33, 0.36 | | Both are LED-lit: whites (217..231, 218, 213..234) neutral to slightly cool; Arrowhead's turf reads yellow-green and saturated, MetLife's cooler and darker. Skin (133..137, 92..96, 76..77). |
| Dome or canopy | BAL at IND, BUF at HOU, NO at DET, GB at MIN, MIA at LV, ARI at LAC (SoFi canopy) | (100, 118, 69), HSV about 82 degrees, 0.42, 0.46 | (63, 85, 58) Ford Field to (105, 130, 78) NRG | Whites the brightest of all buckets (228..246, 225..243, 233..242); even, shadowless light. |

Across every bucket the constants are: turf hue 73..96 degrees (median about 82), turf saturation 0.33..0.56 (median about 0.42), turf value 0.36..0.50, whites neutral (no yellow cast anywhere), skin (120..158, 86..113, 69..86).

## What the game does today (decoded, with evidence)

- The field is drawn as a grass colour map (`color_premipped`, 128x64 P8 inside the `field` scene of every stadium bundle; Arrowhead's median is (100, 125, 66), HSV 73 degrees, 0.47, 0.49, already inside the broadcast range) modulated by a 512x256 P8 tangent-space grass bump map (`detail_normal`, median (127, 128, 219)) that the detail layer alpha-blends over the field, plus the outside grass (`grass_outside_premipped`). Turf stadiums (s02, s06 and five others: 63 bundles) have no colour map and draw the field from the `color_premipped` material's colour word (Baltimore 0xFF37683B, Seattle 0xFF538349).
- The `Fldd` chunk of each bundle carries five colour words; word 2 is the time-of-day tint applied to the field render block and the yard-line scenes (`FUN_0009c160` writes it to material +0x18): day 0xFFFFFFFF, afternoon 0xFFFFEECD, night 0xFFF2FFFF. The afternoon field also bakes (255, 238, 205) into every grass vertex colour.
- Lighting is a table: `FUN_000641c0` (game entry) selects one 0x120-byte rig by indoor, rain, snow, day, afternoon (dynamic sun from the stadium's node) or night, stores it at 0xB34774, and `FUN_000f2360` installs it: ambient colour (+0x00) times intensity (+0x10), light count (+0x14), then per light (stride 0x40 from +0x20) colour, direction and intensity. Retail values: day ambient (0.85, 0.93, 1.00) x 0.285 with a yellow key (1.00, 1.00, 0.72) x 1.2 and a fill (0.85, 1.00, 0.95) x 0.2; night/indoor ambient (0.83, 0.97, 1.00) x 0.31 with three (0.95, 0.95, 1.00) x 0.67 lights; afternoon ambient and key (1.00, 0.92, 0.65) (orange) x 0.27 / 1.0 with two blue fills (0.45, 0.45, 1.00) x 0.15; rain ambient (1.00, 0.86, 0.86) x 0.35 with three (0.79, 0.79, 1.00) x 0.50; snow ambient white x 0.40 with three (0.89, 0.89, 1.00) x 0.34. Night and domes share one table.
- A 9/7 in-game capture on a day stadium measured the near turf at (34, 43, 2) with bright blades at (71, 84, 18): the same hue as the colour map but a third of its value and almost no blue. The yellow key light, the dim ambient and the strong bump contrast are the levers; the colour map itself is close to the broadcast already.
- Fog is separate: the haze table at 0xA867F0 (rows dry [0.0, 0.8, 3000, 6000], rain [0.8, 0.9, 3000, 6000], snow [0.6, 0.8, 3000, 6000]) feeds the camera only when the climate generator produces haze (one dry game in ten). It is owned by the beta-69 haze option and is left alone here.
- The gamma ramp is set once at device creation from a caller-supplied pointer that retail leaves null (`FUN_00033d50`, `FUN_00033e00`); it is not used by this option because xemu's handling of `D3DDevice_SetGammaRamp` is unverified.

## The lighting model per bucket and what the option writes

| Rig (table) | Retail | Broadcast (this option) | Covers |
|---|---|---|---|
| Day (0x4E73B0) | ambient (0.85, 0.93, 1.00) x 0.285; key (1.00, 1.00, 0.72) x 1.20; fill (0.85, 1.00, 0.95) x 0.20 | ambient (0.92, 0.95, 1.00) x 0.45; key (1.00, 0.98, 0.94) x 1.15; fill (0.88, 0.93, 1.00) x 0.30 | 1 PM ET open-air games (measured: TEN, PIT, JAX, CIN, CAR, and the MCG) |
| Afternoon (0x4E7A70, dynamic sun) | ambient (1.00, 0.92, 0.65) x 0.27; key (1.00, 0.92, 0.65) x 1.00; fills (0.45, 0.45, 1.00) x 0.15 | ambient (1.00, 0.95, 0.86) x 0.40; key (1.00, 0.94, 0.84) x 1.10; fills (0.70, 0.78, 1.00) x 0.22 | 4:25 PM ET open-air games (measured: PHI, SEA at 5:20 PM local) |
| Night and indoor (0x4E74D0) | ambient (0.83, 0.97, 1.00) x 0.31; three (0.95, 0.95, 1.00) x 0.67 | ambient (0.94, 0.96, 1.00) x 0.42; three (1.00, 1.00, 1.00) x 0.72 | Night open air (measured: Arrowhead, MetLife) and every dome (measured: IND, HOU, DET, MIN, LV, SoFi). The game uses one table for both; a separate dome rig would need a new table allocation and one operand change at 0x642BE. |
| Rain (0x4E7830) | ambient (1.00, 0.86, 0.86) x 0.35; three (0.79, 0.79, 1.00) x 0.50 | ambient (0.92, 0.93, 0.98) x 0.42; three (0.92, 0.94, 1.00) x 0.62 | Extrapolated: no Week 1 rain game in the references |
| Snow (0x4E7950) | ambient white x 0.40; three (0.89, 0.89, 1.00) x 0.34 | ambient (0.96, 0.97, 1.00) x 0.45; three (0.95, 0.96, 1.00) x 0.55 | Extrapolated: no snow references |
| Alternate day (0x4E75F0) and alternate dynamic (0x4E7710) | ambient (0.83, 0.97, 1.00) x 0.39 / (0.96, 1.00, 0.87) x 0.32; key (1.00, 1.00, 0.78) / (1.00, 1.00, 0.84) x 1.0; fills (0.95, 0.95, 1.00) x 0.37 | ambient (0.92, 0.95, 1.00) x 0.45 / (0.95, 0.97, 1.00) x 0.42; key (1.00, 0.98, 0.94) / (1.00, 0.97, 0.92) x 1.10; fills (0.90, 0.94, 1.00) x 0.40 | The selector's second branch (`FUN_00063fb0` true); which modes reach it is unproved, so these follow the day rig. |

Light directions, light counts and the shadow value at +0x100 keep their retail bytes in every table. The stadium edits are the same for all buckets: colour map and outside grass pulled 35 percent toward hue 82 degrees, saturation x 0.90, value x 1.04; grass bump normals flattened to 55 percent; afternoon tint 0xFFFFEECD to 0xFFFFF5E6 and vertex (255, 238, 205) to (255, 245, 230); night tint 0xFFF2FFFF to 0xFFF8FCFF; the odd (255, 255, 229) vertex tint to (255, 255, 240).

A flat-grass estimate (colour map lit by the rig, before the bump map): day retail (140, 181, 77) to broadcast (160, 200, 105); night retail (180, 231, 128) to (213, 255, 142); afternoon retail (74, 86, 36) to (97, 117, 58). The bump map and the in-game capture suggest the drawn field sits at roughly half of these; that is the comparison Noah should make against the stills.

## What the pins record

477 bundles. Field scene re-graded in 456, kept retail in 21 (the day, day-rain and day-snow variants of alternate
stadium sets s48, s50, s51, s53, s55, s57 and s59: their retail streams leave no room inside the wrapper, and the
loader scratch word must not be raised). Grass bump map flattened in 459, kept retail in 18 for the same reason. Tint
softened in 260 (the 217 day-white tints and one odd dome value are left alone). Every kept span has retail == applied
in the pins, so the option's status stays exact.

## Coverage and extrapolation

Measured and mapped: day open air (six games), late afternoon open air (two), night open air (two, Arrowhead as the anchor), domes (six). Extrapolated: rain and snow rigs (no references), the alternate day/dynamic tables (which modes select them is unproved), and any stadium not in Week 1 (the per-stadium colour maps keep their own hue and only receive the shared pull). The night rig also lights domes because retail shares the table.

## Previews

- `light_rigs_retail_vs_broadcast.png`: every table, retail against broadcast, with the flat-grass estimate.
- `bundle_edits_before_after.png`: decoded colour map, outside grass and bump map for Arrowhead night, MetLife night, Seattle day (turf, material colour word) and Philadelphia afternoon, retail against the bytes the option writes.
- `broadcast_targets_week1.png`: the measured per-game swatches.

## Beta 71 calibration (2026-09-15)

The beta 70 values were measured in game at Arrowhead at night on 2026-09-15: drawn turf (51, 61, 32), HSV 82 degrees /
0.47 / 0.24, against the broadcast (107, 121, 53). The drawn field is far darker than "colour map times rig": with the
beta 70 map (109, 130, 75) under the beta 70 night rig (gain 2.56, 2.56, 2.58 per channel) the flat estimate is
(278, 333, 194), so the screen factor is (0.183, 0.183, 0.165). The 2026-09-07 retail day capture gives the day factor
(0.21, 0.21, 0.21) the same way (blue collapsed under the yellow retail key, so day blue is taken from green). The
module carries both as `SCREEN_FACTOR` and `predicted_on_screen()`; the model reproduces (51, 61, 32) exactly.

Beta 71 therefore lifts the grass colour map through the curve `1 - (1 - v)^2.8` (Arrowhead's median (100, 125, 66)
becomes (181, 216, 102): value 0.49 to 0.85, saturation x 1.12 to 0.53, hue 73 pulled half way toward 72), raises the
night rig to neutral white (ambient 1.0 x 0.50, three lights x 0.86) and the day rig (ambient 0.58, key 1.20, fill
0.48), and makes the night tint neutral (0xFFFFFFFF, vertex (255, 255, 255)). Predicted drawn turf: Arrowhead night
(102, 122, 52) against the broadcast (107, 121, 53); day (83, 99, 47) against (88, 105, 61) (day blue stays low because
one shared map serves every rig; night, Noah's anchor, takes priority). Domes share the night table. Rain and snow rigs
rise by about 12 percent. The bump map flattens to 40 percent (beta 70: 55 percent), which lowers both the darkening
and the amplitude of far-field shimmer; `detail_normal` ships a full mip chain (175,872 bytes for 512x256 P8 plus
palette) and every level shares the one palette, so the flatten is consistent across distances. Whether the shimmer
Noah saw at high internal resolution is retail behaviour or the option's is UNPROVED: it needs an A/B at the same
camera and resolution. The far band of his screenshot carries more high-frequency energy (0.065 normalised) than the
mid field (0.042), which is what detail-layer aliasing looks like, and the same detail layer is drawn by retail.

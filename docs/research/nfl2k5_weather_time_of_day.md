# NFL 2K5 Xbox: weather and time of day

Beta 69 J4, 2026-09-13. **EXPERIMENTAL. Every in-game outcome is UNWITNESSED.**
PROVED below means decoded pinned data or bounded native execution, never a claim
about appearance or a played result. HYPOTHESIS identifies unproved interpretation.

## Result and scope

The disc has an editable stadium climate table with temperature, precipitation
chance and wind. It does not have separate rain and snow probability columns.
The retail franchise selector already reads the schedule hour and selects day,
afternoon or night. Its climate generator also produces an atmospheric value
that reaches existing haze parameters in the camera. Retail already applies
weather penalties to six effective player attributes.

This job supplies a small climate editor, its saved-plan writer and reparsing
verifier, plus a separate optional edit to one existing dry-weather haze
coefficient. Both are OFF by default, EXPERIMENTAL. The protected Build and
registry integration is supplied in [WIRING.md](../../WIRING.md). The independent
editor and CLI work without that integration. No game instructions, hooks,
runtime globals, caves, sky art, gameplay penalties or saves are added or changed.

The editor's **Milder outdoor climate (+2 °F, authored)** example is a controlled
sensitivity preset, not measured modern NFL climate. It affects the first 32
retail home-stadium rows that are outdoors and preserves other fields. It is
idempotent relative to the loaded source and one Undo restores the preceding
draft. A sourced modern climatology preset and modern relocated-stadium climate
assignments remain deferred; no appropriate dataset is pinned on this tree.

To open the independent editor on an extracted game folder or supported disc:

```bash
python3 tools/nfl2k5_weather_editor.py '/path/to/ESPN NFL 2K5 (USA)'
```

Choose a stadium and month, edit the three values, and **Save build edits**.
After the protected integration, Build's **Use saved stadium climate edits
(experimental)** applies that plan to its disposable output. Until then, the
CLI can inspect a source, author the example plan, or apply a plan to a new
exported ROST resource; `--help` lists these copy-only commands.

## Evidence and corrections to the leads

Read-only USA `default.xbe`, 11,948,032 bytes, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
[weather_audit.json](../../reports/b69_j4/weather_audit.json) records every native
span's VA, file offset, size and SHA-256; all 82 decoded climate rows; the 32 team
pointers; all 477 matched stadium bundles; and all 356 matching texture records
with per-wrapper and decoded hashes. It exports no executable, texture pixels or
binary retail fixture. [weather_native.json](../../reports/b69_j4/weather_native.json)
records actual bounded native outputs from this run.

* **PROVED correction:** the beta-33 statements about a city climate table,
  93 stadium sets, 279 skies and a selector that never picks the variants occur
  in the APF bug section of the hub `AI_HANDOFF.md` (around line 234). The adjacent
  player/ability discussion and PowerPC addresses identify that game. They cannot
  be transferred to this Xbox executable.
* **PROVED:** `tools/nfl_group36_xemu_runtime_result.py` identifies `s42nd.iff`
  as Night/Clear, outer 3280. This independent archive scan resolves the same
  outer, ID `e4d6b0bc`, virtual offset `0xd550a000`
  (3578830848), size 1,390,448. This is a naming/archive cross-check, not a new
  runtime witness or endorsement of that earlier tool's visual conclusions.
* **PROVED correction:** the ESPN 25 editor's `SETUP` dictionary does not expose
  weather, but the native scenario record does contain weather at +0x60, time of
  day at +0x64 and signed temperature at +0x68. The existing scenario research maps
  their loads. Adding a dictionary field alone would not prove franchise routing.
* The retail preset enum has six choices: Clear, Light Rain, Heavy Rain, Flurries,
  Heavy Snow, Random. Clear/Rain/Snow are the three resulting asset suffix families.

## Climate storage and native interpretation

**PROVED:** main ROST, outer 5 in pack 0, retail virtual offset `0x392800`, span
`0x90f80` including its 32-byte wrapper; uncompressed body `0x90f60`.
The inner `ROST` marker is resource +0x2c, version 17 at +0x30, root self-relative
pointer at +0x34. A relative pointer resolves as `field + signed_value - 1`.
Retail root is +0x60. Root +0x10 is count 82; root +0x14 resolves the stadium
pool at resource +0xd0. Stadium stride is 0x80. The table's retail SHA-256 is
`44d6e8566dc6902dd1f12dbe2625014687cc99f375559415231f72a634631cd2`.
It is relocated data, so it has no fixed heap VA. The active stadium pointer is
`[0xE5FE64]`; the generator receives that pointer in ECX.

| Row offset | Meaning | Proof / ownership |
|---|---|---|
| +0x00 | Stadium name pointer | Decoded UTF-16; preserved |
| +0x04 | Numeric field | Not a pointer; semantics unowned |
| +0x08 | City name pointer | Decoded UTF-16; preserved |
| +0x0c | Asset prefix pointer, e.g. `s05` | Native filename reader; preserved |
| +0x10 / +0x14 | Descriptive name / created-field logo prefix | Pointer fields; preserved |
| +0x18 | Indoor/roof word | Native indoor weather reset and haze bypass |
| +0x1c..+0x27 | Other metadata | Pinned and preserved; semantics unowned |
| +0x28..+0x43 | Seven temperature floats | Fahrenheit baseline; editable |
| +0x44..+0x5f | Seven precipitation threshold floats | Percent units; editable |
| +0x60..+0x7b | Seven wind floats | Native speed; editable, UI converts to mph |
| +0x7c | Asset/stadium identifier byte | Pinned; preserved |

Each stadium row carries its own climate. There is no separate city-to-climate
index here; rows can share names or artwork while retaining separate floats.
NFL team record +0x114 points to a stadium row. The decoded team-to-row table is
appended below. The audit also includes alternate/historic rows 32..81, rather
than silently treating them as current NFL cities.

Month lookup at `0x4F6530` is 13 signed integers:
`[-1,5,6,-1,-1,-1,-1,0,0,1,2,3,4]` for month values 0..12.
Slot order is **July/August, September, October, November, December, January,
February**. March..June have -1 entries and are refused by the writer. They are
not independent months that can be safely exposed. There is no snow-probability,
humidity or independent fog-chance column in this record.

**PROVED native reader:** `0xEC870..0xEC9ED`, 382 bytes, ECX stadium, EDX month,
stack time-of-day and output pointer. Four outputs:

1. Temperature baseline plus a native random offset selected by time of day:
   day [-5,+15), afternoon [-10,+10), night [-20,0), from `0x4F6564`.
2. Precipitation intensity. A random 0..100 comparison against the stored
   percentage decides precipitation. A separate draw against half that
   percentage chooses heavy [0.6,1) versus light [0.1,0.35). Otherwise zero.
   Thus the same threshold influences occurrence and heavy/light mix. Boundary
   comparison is inclusive, so a table value of 0 is not a formal exclusion of
   an exactly-zero RNG draw. The editor does not promise a guaranteed clear sky.
3. Wind baseline times `(0.1 + 1.05 * U)`, with a separate one-in-eight zero-wind
   branch. `0x25E3ED` divides the game value by float `44.704` at `0x4F267C` for
   the `%s will defend. Wind %d mph.` string at `0xE8B490`. This proves the UI
   conversion; native speed has the cm/s-to-mph scale. A baseline is not a
   requested exact live wind speed.
4. Haze amount: when wet, `U * precipitation`; when dry, an approximately one-in-ten
   branch supplies [0.1,0.25), otherwise zero. Its downstream camera reader is
   proved below. It is generated code, not a fourth table array.

For example, Chicago row 5 (`s05`, resource +0x350) has temperature baselines
73.4, 66, 54.2, 41.4, 28.1, 22.4, 22.4; precipitation thresholds
26, 23, 23, 30, 33, 33, 33; native wind baselines
277.1, 312.9, 326.3, 406.8, 415.7, 438.1, 438.1. These are rounded presentations;
the audit keeps decoded float precision and the writer compares float32 bytes.

## Who writes and reads the weather state

There is no single universal weather word. The menu preset is an enum; gameplay
and artwork mostly consume generated floats and predicates.

| VA | Type / role | Proved writers / readers |
|---|---|---|
| `0xE601D0` | Menu weather preset 0..5 | Menu arrows; `0xE3150`; scenario +0x60 |
| `0xE60184` | TOD enum 0 day, 1 afternoon, 2 night | `0x133FF9`, menu, scenario +0x64; `0xE3130/40` |
| `0xE5FFA4` | Float temperature | `0x134018`, `0xE3150`; rain/snow classifier |
| `0xE5FFAC` | Float precipitation intensity | `0x13401D`, `0xE3150`; artwork, haze, effective attributes, ball paths |
| `0xE600C0` | Float wind magnitude | `0x134023`, `0xE3265`; display and ball vector readers |
| `0xE60088` | Wind direction integer | Helper `0xE2DB0`; trig/vector readers |
| `0xE600C4` | Float haze amount | `0x134032`; `0x85EF0` renderer parameter reader |
| `0xE5FE64` | Active stadium pointer | Stadium setter `0x77470`; climate and asset selection |

**Play Now, PROVED:** arrow writers `0x14C110/0x14C140`, and duplicate screen
callbacks `0x2C2CA0/0x2C2CD0`, `0x340410/0x340440`, wrap the preset from 0..5.
Label pointers are at `0x4F2524`. `0xE3150` uses September climate except Random
chooses month 9..12, then explicitly overrides precipitation to zero, light
[0.25,0.45], or heavy [0.5,1]. Rain/snow presets adjust temperature; the six
native cases and classifier results pass. It supplies wind in the 1..4 mph
range. It does not copy the climate output's fourth float to `0xE600C4`.
Whether another frontend path clears a prior haze value is **HYPOTHESIS**.

`0x77BB0` is snow: precipitation >0 and temperature <=35 °F.
`0x77BE0` is rain: precipitation >0 and temperature >35 °F.
The native boundary tests include 35 and 35.01. No claim of physical freezing
point fidelity follows from the retail threshold.

**Franchise, PROVED:** `0x15DB50..0x15DBE1` gets the home team's stadium from
team +0x114, calls stadium setter `0x77470` at `0x15DB9F`, and climate/time
initializer `0x133FC0` at `0x15DBB6`. The initializer generates the above globals
afresh. Merely setting the Play Now preset is insufficient for this path.
`0x134040` and following setup paths also serialize/copy generated values; this
job does not claim an exhaustive mode/save lifecycle or persistence map.

## Schedule time, stadium and sky selection

**PROVED:** `0x133FC0` receives week in ECX, game in EDX and reads the eight-byte
game record at `0xE57C40 + 8 * (17 * week + game)`. Record +6 is hour; +3 is
month. Minute +7 is not read for the TOD decision.

| Encoded hour | Retail result |
|---|---|
| 0..3, 11, 12 | 0, day |
| 4..5 | 1, afternoon |
| 6..10 | 2, night |

All 272 entries of `data/nfl_2026_schedule.json` were run through that native
decision, along with 13 hour values and four minute values. The usual 1 pm,
4 pm and evening slots produce all three variants. **No selector-enabling patch
is needed or shipped.** There is no evidence that 2K5's selector never picks
the shipped afternoon/night variants. A separate within-game dynamic sunset
controller is not established by this initialization routine.

**PROVED limitation:** the schedule's eight-byte record does not store an AM/PM
flag. Its 9:30 AM London-style entries carry hour 9 and select night in this
reader; 11 AM entries select day. A blanket hour-9 patch would also alter 9 PM.
A future bounded fix needs the date/game identity or an owned AM discriminator
through schedule generation and saves. This job adds no such hook or schedule
writer. Venue substitutions, save reload and lighting remain UNWITNESSED.

`0x62BE0` copies the current settings into `0xB30850..0xB30860`, then builds
weather character `d/r/s` via the rain/snow predicates and time character
`d/a/n` via `0xE3140/0xE3130`. `0x62C71` enters formatting using the UTF-16
format `%s%c%c.iff` at `0xE610A0` and the stadium prefix at row +0x0c; result
buffer `0xB306D0`. Created field art uses `ct%s%c.iff` at `0xE610B8`, from +0x14.
The harness runs the actual suffix selection and stops before formatting.
Pinned format bytes and matched archive CRCs establish the corresponding names.

At `0x62CC5` the indoor word is tested. `0x62CCC..0x62CF3` resets wind,
precipitation and haze to zero and temperature to 70 **after** computing the
bundle name. Indoor stadiums having rain/snow bundle names therefore does not
prove wet indoor gameplay or rendering. The eight NFL roof rows are Atlanta,
Dallas, Detroit, Indianapolis, Minnesota, New Orleans, St. Louis and Houston.
The writer preserves their roof words exactly.

### Bounded on-disc sky list

The tool computes the archive's uppercase UTF-16LE CRC32 for all
`s00..s99 × {d,a,n} × {d,r,s}.iff`, then walks every wrapper of each match and
fully decodes each bounded standalone TXTR before reading its texture name.
**PROVED: 53 prefixes × 9 combinations = 477 stadium bundles.**
Those 53 prefixes exactly match the unique asset-prefix set of all 82 climate
rows; no stadium row's prefix is missing from this nine-combination inventory.
There are **324 textures named `sky` (36 × 9)**, plus **32 named `cloud`**,
with 19 distinct decoded payload hashes across the two names. Nothing is
inferred about how distinct hashes look.

Sky-bearing prefixes, each with `dd, dr, ds, ad, ar, as, nd, nr, ns`:
`s00 s02 s03 s04 s05 s06 s07 s08 s09 s10 s12 s13 s14 s16 s18 s19 s20 s21
s22 s24 s25 s26 s27 s28 s29 s30 s31 s32 s37 s39 s40 s41 s42 s43 s44 s45`.
The audit lists every exact outer index, bundle, chunk ordinal, relative chunk
offset and hash. Skies are within these stadium bundles; the APF claim of a
separate 279-set sky list is not reproduced here.

No decoded texture name in this bounded inventory says `fog`, `overcast` or
`dusk`. This is **not** an exhaustive unknown-filename or nested-material oracle,
nor a visual classification of the `sky` textures. No overcast/dusk artwork
option is shipped. Afternoon is an existing suffix, not proof of dynamic sunset.

## Existing haze parameter: separate optional data edit

**PROVED:** native reader `0x85EF0..0x85F8F` selects one of three rows:

| Row VA | Eligibility | Density endpoints | Start / end |
|---|---|---|---|
| `0xA867F0` | Dry outdoor, nonzero haze | 0, 0.8 | 3000, 6000 |
| `0xA86804` | Rain | 0.8, 0.9 | 3000, 6000 |
| `0xA86818` | Snow | 0.6, 0.8 | 3000, 6000 |

Each row also has a packed color. The reader computes
`base + (endpoint - base) * [0xE600C4]`, writes `0xA86734`, and copies start,
end and color to `0xA86738/3C/40`. Indoor and clear-with-zero-haze paths use zero.
`0x86190` calls `0x2B9E0`, which places density/start/end/color into camera
+0x2a0/+0x298/+0x29c/+0x2a4. Native execution stops at `0x2BA04`, before the
graphics-state refresh. It proves camera fields, not GPU state or visibility.

`nfl2k5_weather_haze.py` edits **only float `0xA867F4`: 0.8 → 1.0** in `.data`,
and repairs that section's SHA-1 header digest. It recognizes retail/already
applied bytes, pins the normalized 60-byte table and three reader spans, and
reparses on verification. Off exactly restores a recognized installation.
There is no `REQUESTS` allocation because no new runtime storage/code is used.
The cave manifest must be regenerated by integration to record this existing
four-byte ownership, not an invented cave.

The actual native test at dry haze 0.25 changes camera density 0.20 → 0.25.
Tested rain remains 0.825, snow 0.65, indoor zero and zero-haze clear zero.
This does not force fog. “Existing dry-weather haze response (experimental)”
is the supported caption; “fog weather,” “overcast,” or claims of appearance
would overstate the proof. A played comparison is required to judge whether
this small existing lever is useful.

## Gameplay consumers: research only

**PROVED native mechanism:** the effective-rating loop at `0x17A6D0` iterates
28 descriptors at `0xAA4020`, stride 32. Descriptor +8 is the raw rating reader,
+0x10 flags. At `0x17A84B`, precipitation >0 and flag bit 0 enable an additive
penalty to the current intermediate rating. The local base at stack +0x10 is
reduced by `0.10 * precipitation` for rain or `0.15 * precipitation` for snow,
then later processing continues. With input base 0.8 and intensity 0.5, native
outputs are 0.75 rain and 0.725 snow; no flag or dry returns 0.8.

| Descriptor | Raw player offset | Reader VA | Weather flag |
|---|---|---|---|
| Speed (0) | +0x36 | `0x179840` | Yes |
| Agility (1) | +0x37 | `0x1798B0` | Yes |
| Catching (4) | +0x44 | `0x179990` | Yes |
| Pass accuracy (5) | +0x42 | `0x179A70` | Yes |
| Kick accuracy (8) | +0x4a | `0x179BC0` | Yes |
| Hold onto ball (10) | +0x47 | `0x179CA0` | Yes |
| Arm strength (6) | +0x38 | `0x179AE0` | No |
| Kick power (7) | +0x3a | `0x179B50` | No |

All 28 flags and raw-reader hashes are recorded in the audit. The harness enters
the penalty block with controlled descriptor flags and intermediate base; it
does not run the complete rating refresh, final clamps, animations, contacts or
plays. Thus changed catch/fumble counts, traction or yardage remain UNWITNESSED.
Speed/agility penalties are not proof of a separate surface-friction simulation.

Additional **PROVED reads, HYPOTHESIS about final gameplay semantics**:

* `0x1C75B7..0x1C75F8` interpolates a contact probability input toward 0.08 in
  rain or 0.10 in snow using precipitation. It lies in `0x1C7470`, called from
  collision processing at `0x1CD40B`. The native interpolation is also executed:
  starting from 0.05, dry stays 0.05, intensity 0.5 rain gives 0.065 and snow
  gives 0.075. This fixture assumes the preceding collision eligibility checks
  already passed. It stops at `0x1C7659` before rating/slider scaling.
  The pinned continuation reads hold-onto-ball (descriptor 10 through
  `0x17B010`), its table `0x50B59C`, and `[0xE60208]`, mapped as Fumble by
  `tools/nfl2k5_xbox_save_inventory.py`, through table `0x50B5E0`. It then
  clamps/transforms the input and calls native random comparison `0x1C5550`
  at `0x1C76CB`. On success it calls `0x1CC4D0` and event route `0xA10F0`.
  This establishes a fumble-related probability path, not a friction/bounce
  coefficient. Final turnover activation and its complete probability remain
  unexecuted; no traction slider is justified.
* `0x1DB968..0x1DB9E3` selects and blends weather/rating tables at
  `0x50B61C/0x50B640` and `0x50B688/0x50B6AC`. Catch/contact context is a lead,
  not a proved final drop probability.
* `0x1DA057..0x1DA072` sets a local 0.2 when precipitation is positive.
  Handling/fumble interpretation remains a lead, separate from the proved
  hold-onto-ball effective-rating penalty.
* `0x1CB7C5..0x1CB819` and `0x1CBA1E..0x1CBA7D` consume wind magnitude and
  direction, use trig helper `0x1C8E90`, and feed vector components including
  `0xBE5BA0/0xBE5BA8`. Ball integration plausibly changes passing/kicking,
  but neither a kick-distance formula nor an outcome was executed here.

Smallest localized research lever: the existing rain contact target, immediate
float 0.08 at `0x1C75E2` inside instruction `0x1C75DE` (snow's 0.10 is at
`0x1C75D8`). A future writer could pin the full instruction/path, change that
one literal and re-run the interpolation and downstream probability reader.
It must first prove collision eligibility and the final turnover event before
claiming useful fumble tuning. The six effective-rating penalties offer another
lead, but their shared constants require a reference audit. **No gameplay writer
is shipped.** The climate authoring itself already supplies the native
retail generator with different weather inputs; its downstream balance is
unwitnessed and it must stay experimental.

## Franchise menu choice: pinned wall, not a shipped toggle

The Weather row exists. Descriptors `0x502A38`, `0x526BAC`, `0x526EC4` and
`0x54FCC8` reference the above arrow callbacks. In the mode/network filter
`0x2C1140`, mode 6/7 jump table `0x2C1200` routes to `0x2C11BF`: it suppresses
Stadium and Time Of Day, then Weather at `0x2C11D9` via `0xF2F90`.
That label lookup marks menu row +0x18 at `0xF2FE0` and dispatches event 0x13.
Mode labels and full frontend lifecycle remain only partially mapped.

Even if this row were unhidden, the franchise initializer `0x133FC0` replaces
the live values using the stadium/month. Calling Play Now's `0xE3150` blindly
would substitute September for the franchise's actual month on explicit
presets. A correct option needs a persistent Off/override state, a proved
game-day screen route, correct initialization order, and return/reload handling.
No bounded complete lifecycle or safe unused slot was proved here. Therefore
**no “Choose weather in franchise” option or ineffective no-op is registered**.
The editor supplies per-stadium/month data authoring, not a pregame selector.

## Harness reach and witness plan

The Unicorn fixture maps retail sections, preserving whole-page permissions;
provides one synthetic stadium row, schedule entries, stack and camera; seeds
the native RNG state; and executes retail code with a 20,000-instruction budget
per call. No RNG, classifier or selector is stubbed. It fails if a stop boundary
is not reached. It covers all 82 rows × 7 months × 3 time slots, schedule hour
and minute boundaries, all 272 template games, six menu presets, edited snow
selection, camera field copies, and the bounded rating penalty block.

It cannot reach a real frontend/controller flow, save lifecycle, stadium load,
graphics submission, appearance, animation or complete football play. No
emulator, displayed GUI, audio or network was used for this job.

Player witness list, all **UNWITNESSED**:

1. Build a disposable disc using the saved climate plan, then create a new
   franchise. At Chicago in December, compare the baseline with the receipt's
   controlled example (15 °F baseline, 100% precipitation threshold, 12 mph
   wind baseline). Record the actual pregame conditions and whether the game
   starts and returns normally. These are randomized baselines, not exact
   promises for the pregame readout.
2. Compare 1 pm, 4 pm and evening scheduled games at the same outdoor stadium.
   Record loaded day/afternoon/night selection and a screenshot if useful.
   This witnesses retail schedule selection, not a newly enabled option.
   Include a 9:30 AM international slot to confirm the encoded-hour limitation.
3. Repeat wet/cold authored data at an indoor stadium. Confirm what the game
   reports and how it handles the roof path; no wet-indoor outcome is promised.
4. With haze Off/On on equivalent nonzero dry outdoor conditions, record a
   played comparison. Do not claim an improvement if no visible change is
   observed. Include zero haze, rain, snow and an indoor control. Native camera
   coefficients alone do not predict a screenshot.
5. Preserve an existing save and compare its weather to a newly created
   franchise. Existing-save adoption of the edited disc table is unproved.
   Do not edit or replace that save to manufacture a witness.
6. For gameplay research, compare recorded inputs, wind direction, player
   ratings, difficulty and sliders across dry/rain/snow games. A few changed
   catches or fumbles are not a proof of the exact probability model. No new
   gameplay feature or snow-footprint effect is claimed.

## Decoded row and pin tables

The following tables are generated from this job's audit. The full JSON has
every per-month float; the compact row table identifies all stadiums and their
actual retail team associations. “Unused NFL” means no first-32-team pointer,
not proof that a stadium is unreachable in another mode.

| Row | Resource offset | Prefix | Stadium | City | Roof | NFL team |
|---|---|---|---|---|---|---|
| 0 | 0xd0 | s00 | Arizona Stadium | Tempe, AZ | Outdoor | Cardinals |
| 1 | 0x150 | s01 | Georgia Dome | Atlanta, GA | Indoor | Falcons |
| 2 | 0x1d0 | s02 | M&T Bank Stadium  | Baltimore, MD | Outdoor | Ravens |
| 3 | 0x250 | s03 | Ralph Wilson Stadium | Orchard Park, NY | Outdoor | Bills |
| 4 | 0x2d0 | s04 | B of A Stadium | Charlotte, NC | Outdoor | Panthers |
| 5 | 0x350 | s05 | Chicago Field | Chicago, IL | Outdoor | Bears |
| 6 | 0x3d0 | s06 | Paul Brown Stadium | Cincinnati, OH | Outdoor | Bengals |
| 7 | 0x450 | s07 | Texas Stadium | Irving, TX | Indoor | Cowboys |
| 8 | 0x4d0 | s08 | INVESCO Field | Denver, CO | Outdoor | Broncos |
| 9 | 0x550 | s09 | Ford Field | Detroit, MI | Indoor | Lions |
| 10 | 0x5d0 | s10 | Lambeau Field | Green Bay, WI | Outdoor | Packers |
| 11 | 0x650 | s11 | RCA Dome | Indianapolis, IN | Indoor | Colts |
| 12 | 0x6d0 | s12 | ALLTEL Stadium | Jacksonville, FL | Outdoor | Jaguars |
| 13 | 0x750 | s13 | Arrowhead Stadium | Kansas City, MO | Outdoor | Chiefs |
| 14 | 0x7d0 | s14 | Pro Player Stadium | Miami, FL | Outdoor | Dolphins |
| 15 | 0x850 | s15 | H. H. H. Metrodome | Minneapolis, MN | Indoor | Vikings |
| 16 | 0x8d0 | s16 | Gillette Stadium | Foxboro, MA | Outdoor | Patriots |
| 17 | 0x950 | s17 | Louisiana Super Dome | New Orleans, LA | Indoor | Saints |
| 18 | 0x9d0 | s18 | Giants Stadium | East Rutherford, NJ | Outdoor | Giants |
| 19 | 0xa50 | s19 | Jets Stadium | East Rutherford, NJ | Outdoor | Jets |
| 20 | 0xad0 | s20 | Network Associates | Oakland, CA | Outdoor | Raiders |
| 21 | 0xb50 | s21 | Lincoln Financial Field | Philadelphia, PA | Outdoor | Eagles |
| 22 | 0xbd0 | s22 | Heinz Field | Pittsburgh, PA | Outdoor | Steelers |
| 23 | 0xc50 | s23 | Edward Jones Dome  | St. Louis, MO | Indoor | Rams |
| 24 | 0xcd0 | s24 | QUALCOMM Stadium | San Diego, CA | Outdoor | Chargers |
| 25 | 0xd50 | s25 | San Francisco Park | San Francisco, CA | Outdoor | 49ers |
| 26 | 0xdd0 | s26 | Qwest Field | Seattle, WA | Outdoor | Seahawks |
| 27 | 0xe50 | s27 | Tampa Bay Stadium | Tampa, FL | Outdoor | Buccaneers |
| 28 | 0xed0 | s28 | Titans Coliseum | Nashville, TN | Outdoor | Titans |
| 29 | 0xf50 | s29 | Washington Field | Raljon, MD | Outdoor | Redskins |
| 30 | 0xfd0 | s30 | Cleveland Stadium | Cleveland, OH | Outdoor | Browns |
| 31 | 0x1050 | s37 | Reliant Stadium | Houston, TX | Indoor | Texans |
| 32 | 0x10d0 | s31 | Aloha Stadium | Honolulu, HI | Outdoor | Unused NFL |
| 33 | 0x1150 | s32 | Practice Facility  | San Rafael, CA | Outdoor | Unused NFL |
| 34 | 0x11d0 | s39 | Future Aloha Stadium | Honolulu, HI | Outdoor | Unused NFL |
| 35 | 0x1250 | s40 | Super Bowl 2005 | Jacksonville, FL | Outdoor | Unused NFL |
| 36 | 0x12d0 | s42 | Super Bowl 2006 | Detroit, MI | Indoor | Unused NFL |
| 37 | 0x1350 | s43 | Super Bowl 2007 | Miami, FL | Outdoor | Unused NFL |
| 38 | 0x13d0 | s41 | Super Bowl 2008 | Tempe, AZ | Outdoor | Unused NFL |
| 39 | 0x1450 | s44 | Super Bowl Future | Los Angeles, CA | Outdoor | Unused NFL |
| 40 | 0x14d0 | s45 | Ulterior Super Bowl | San Jose, CA | Outdoor | Unused NFL |
| 41 | 0x1550 | s36 | Visual Concepts Dome | San Rafael, CA | Indoor | Unused NFL |
| 42 | 0x15d0 | s48 | ESPN Stadium | Bristol, CT | Indoor | Unused NFL |
| 43 | 0x1650 | s54 | Cheesesteak Dome | Upper Darby, PA | Indoor | Unused NFL |
| 44 | 0x16d0 | s55 | Loco Arena | Los Angeles, CA | Indoor | Unused NFL |
| 45 | 0x1750 | s56 | Electra Coliseum | Cincinnati, OH | Indoor | Unused NFL |
| 46 | 0x17d0 | s57 | Funk Field | Baurtwell, NY | Indoor | Unused NFL |
| 47 | 0x1850 | s58 | Dream Superdome | Los Angeles, CA | Indoor | Unused NFL |
| 48 | 0x18d0 | s51 | Alien Arena | Roswell, NM | Indoor | Unused NFL |
| 49 | 0x1950 | s52 | Atomic Dome | Alamogordo, NM | Indoor | Unused NFL |
| 50 | 0x19d0 | s53 | Metro Field | Hickory, NC | Indoor | Unused NFL |
| 51 | 0x1a50 | s54 | Bat Field | Kenosha, WI | Indoor | Unused NFL |
| 52 | 0x1ad0 | s55 | Axe Superdome | Boise, ID | Indoor | Unused NFL |
| 53 | 0x1b50 | s56 | Angry Dog Park | Santa Barbara, CA | Indoor | Unused NFL |
| 54 | 0x1bd0 | s57 | Express Dome | Salt Lake City, UT | Indoor | Unused NFL |
| 55 | 0x1c50 | s58 | Cat Park | Salem, MA | Indoor | Unused NFL |
| 56 | 0x1cd0 | s59 | Cobra Field | San Jose, CA | Indoor | Unused NFL |
| 57 | 0x1d50 | s50 | Royal Arena | Los Angeles, CA | Indoor | Unused NFL |
| 58 | 0x1dd0 | s51 | Dragon Dome | Portland, OR | Indoor | Unused NFL |
| 59 | 0x1e50 | s52 | Gold Coast Dome | Monterey, CA | Indoor | Unused NFL |
| 60 | 0x1ed0 | s53 | Scimitar Stadium | Brooklyn, NY | Indoor | Unused NFL |
| 61 | 0x1f50 | s54 | Rebel Field | Birmingham, AL | Indoor | Unused NFL |
| 62 | 0x1fd0 | s55 | Jester Park | Atlantic City, NJ | Indoor | Unused NFL |
| 63 | 0x2050 | s56 | Knight Field | Bloomington, IN | Indoor | Unused NFL |
| 64 | 0x20d0 | s57 | Thunderbolt Park | Branson, MO | Indoor | Unused NFL |
| 65 | 0x2150 | s58 | Norseman Stadium | Las Vegas, NV | Indoor | Unused NFL |
| 66 | 0x21d0 | s59 | Star Dome | Anaheim, CA | Indoor | Unused NFL |
| 67 | 0x2250 | s50 | Viper Stadium | Long Beach, CA | Indoor | Unused NFL |
| 68 | 0x22d0 | s51 | Firecracker Dome | Reno, NV | Indoor | Unused NFL |
| 69 | 0x2350 | s53 | Arachnid Park | Palm Springs, CA | Indoor | Unused NFL |
| 70 | 0x23d0 | s54 | Diablo Coliseum | Devil's Tower, WY | Indoor | Unused NFL |
| 71 | 0x2450 | s55 | Rhino Park | Jackson Hole, WY | Indoor | Unused NFL |
| 72 | 0x24d0 | s56 | Ariel Superdome | Helena, MT | Indoor | Unused NFL |
| 73 | 0x2550 | s57 | Rising Sun Coliseum | Flagstaff, AZ | Indoor | Unused NFL |
| 74 | 0x25d0 | s58 | Gator Coliseum | Gainesville, FL | Indoor | Unused NFL |
| 75 | 0x2650 | s59 | Outback Field | Sacramento, CA | Indoor | Unused NFL |
| 76 | 0x26d0 | s54 | Southwest Dome | Grand Canyon, AZ | Indoor | Unused NFL |
| 77 | 0x2750 | s55 | Mercury Stadium | San Antonio, TX | Indoor | Unused NFL |
| 78 | 0x27d0 | s56 | Prehistoric Park | Anchorage, AK | Indoor | Unused NFL |
| 79 | 0x2850 | s57 | Iron Hammer Coliseum | Zion, UT | Indoor | Unused NFL |
| 80 | 0x28d0 | s58 | Hog Heaven | Little Rock, AR | Indoor | Unused NFL |
| 81 | 0x2950 | s59 | Zoo Dome | Orlando, FL | Indoor | Unused NFL |

### Native byte pins

SHA-256 hashes cover the exact indicated byte spans in the retail file. Runtime globals above lie in zero-fill storage and have no meaningful retail initialized-byte pin.

| VA | File offset | Bytes | Purpose | SHA-256 |
|---|---|---|---|---|
| `0x00133fc0` | `0x123fc0` | 124 | schedule climate initializer | `79a8042a91a545c7007eed49fcf63d85a4b70efa3b48dad274a410f7a69ae7e6` |
| `0x0015db50` | `0x14db50` | 146 | franchise game setup caller | `d963a533b611c72a7115b51f87ed1304aa9b2aef4a29c7690d1d8a9fb33c6422` |
| `0x000ec870` | `0xdc870` | 382 | climate generator | `cdac3f6d6b1c1d5e68ffdeebd1f76a75ca7c09f7dda6969deb1ea362b17e2af1` |
| `0x004f6530` | `0x4eba50` | 52 | month lookup | `522714b8a1ccf37904b2028f805d6ad3bee4becc97b8395b56e75f3b31700a82` |
| `0x004f6564` | `0x4eba84` | 24 | time temperature ranges | `c22ac1432f759f9350472e04dbf374f0835f200b1eb497fb2e3bcd3857296e1a` |
| `0x000e3150` | `0xd3150` | 312 | Play Now weather generator | `30ddae291a46aa596297f38b0e1303301be106ae77012c5b884610957894dece` |
| `0x004f2524` | `0x4e7a44` | 24 | weather label pointers | `424e588384021f9fce3f3610b14caa1a018d1976b23b6037a934f85a89d750fd` |
| `0x00077bb0` | `0x67bb0` | 95 | snow and rain classifiers | `5c18644f31c7c71ac8aa3c5b389788ce29be30d9487932e3a6fa8f4528da9e5f` |
| `0x000e3130` | `0xd3130` | 31 | night and afternoon predicates | `86582c5004a7e1f2d7d624f31d145f1f0c5ac4124951282ff1d89dbbd5378ce0` |
| `0x00062be0` | `0x52be0` | 276 | stadium suffixes and indoor reset | `8d6d9dda83a1b4d88551451f4631adaacaac9311ab5e24e75139696fede6409a` |
| `0x002c1140` | `0x2b1140` | 211 | mode and network weather row suppression | `98edf2c8479f0d3b891979de9a5620085acf2c205c0936b0dd909096159d36ea` |
| `0x00085ef0` | `0x75ef0` | 160 | haze reader | `9a6c2b318862584e4831c20c289a3686cf206dc63df001a3cc57bf0758944777` |
| `0x00086190` | `0x76190` | 35 | haze camera dispatch | `a2dd6d42a842bb0da56a1acb2da8b76580acd0dd73b4769bb5a0fa15922374ae` |
| `0x0002b9e0` | `0x1b9e0` | 44 | camera haze fields | `136c6e1c847abc3701cb03299d6b8585a18e634701e6ca64c203de4f8f351b07` |
| `0x00a867f0` | `0xa7be70` | 60 | three haze parameter rows | `311636b9459867b8fb1fb57be66e6bee17660119754995f678f8f9e1f6642520` |
| `0x0017a84b` | `0x16a84b` | 73 | conditional precipitation penalty candidate | `c8c138e8ae989447257c9bfacd60c5badc0df8c37fa68876f8b4c1d9ccfb4afd` |
| `0x001c75b7` | `0x1b75b7` | 69 | wet ball contact interpolation | `e37caf541c6376d46cbb4aca84418820f156827f6bfc5ea3a6109b623d2ea6ea` |
| `0x001da057` | `0x1ca057` | 27 | wet handling candidate | `f012902cc60e8ab8b9f6240890d7fa2f6b66106f9c401a406ddf20b844dd5a1e` |
| `0x001cb7c5` | `0x1bb7c5` | 90 | wind vector candidate | `5e69681e4792727609582a10c7b38f8b5aa739c3de0b52692b89fa4a8d6a0cdc` |
| `0x001cba1e` | `0x1bba1e` | 95 | second wind vector candidate | `b9ade47a33b290d90f2bbe1ef0d499e8ee0dd837cc346ca8f3617be2a0e83e3f` |
| `0x00aa4020` | `0xa996a0` | 896 | 28 effective-rating descriptors; precipitation flag bit 0 | `03bf7526cbdad23e9574d87db9a35bad73a9367f14b5bf2e3180904f61d8c599` |
| `0x0025e3d4` | `0x24e3d4` | 137 | wind display divides native speed by 44.704 | `59a43161d24fa3d31ec24c9a4a3b4b97763673b333ec6fb44f69e202fe7314e9` |
| `0x004f267c` | `0x4e7b9c` | 4 | wind units per mph | `7c7d3deeaf065ff79ed7bde75182afab04cf390183c1bc5b46cd8aa3c3e62759` |
| `0x00e8b490` | `0xb1a170` | 60 | wind display format with mph unit | `16ee1079c287a822d51437643f70cfa408efa2042efd64c5887d497b47d2bf83` |
| `0x0014c110` | `0x13c110` | 82 | weather menu previous/next callbacks | `39ee5407d1fee5c824aa47970bcad608013ac0eb4e47c550dd95b4d2aa974981` |
| `0x002c2ca0` | `0x2b2ca0` | 82 | second weather menu previous/next callbacks | `39ee5407d1fee5c824aa47970bcad608013ac0eb4e47c550dd95b4d2aa974981` |
| `0x00340410` | `0x330410` | 82 | third weather menu previous/next callbacks | `39ee5407d1fee5c824aa47970bcad608013ac0eb4e47c550dd95b4d2aa974981` |
| `0x000f2f90` | `0xe2f90` | 112 | menu row disable and event dispatch | `efc9813a20ce4404b2af9baa1f66da33f72af332a532784602d2c7cc4a87bc1f` |
| `0x002c1200` | `0x2b1200` | 32 | mode filter jump table | `242a49ff0af6db8e527d15fa645321c6d317802eb617bf962aad12d368304d07` |
| `0x00502a38` | `0x4f7f58` | 32 | quick-game weather menu descriptor | `04a63e443ee9c9752c48226cbb37c8acf0587a221a9c8576cd41035399ec9dc7` |
| `0x00526bac` | `0x51c0cc` | 32 | weather menu descriptor | `024ff8e13358ba4e93bd824208f1b838e1a605e6bf2c3fd6bc310f1bba3787d9` |
| `0x00526ec4` | `0x51c3e4` | 32 | alternate weather menu descriptor | `024ff8e13358ba4e93bd824208f1b838e1a605e6bf2c3fd6bc310f1bba3787d9` |
| `0x0054fcc8` | `0x5451e8` | 32 | additional weather menu descriptor | `4713b3f6bcf8c97da218381ebb92b1f9fa00306ebe5a1bc074c184e514a399f8` |
| `0x0020cbd0` | `0x1fcbd0` | 160 | ESPN scenario environment loads | `f03d6eb97861ca3d06264c0ac8fce50c1194e69d350fadb6650f2a5cda50f60b` |
| `0x0017a6d0` | `0x16a6d0` | 452 | effective-attribute loop through precipitation block | `1a23ad6b877d27e0169b4ea6bc2c5b588991b6618db3bb14cdf2a5da114ab2eb` |
| `0x001db968` | `0x1cb968` | 124 | weather-dependent rating table blend | `a97d947d493d9ff70900e61e208a1928d1095b8288cb7720414f2855ee1c4300` |
| `0x00e610a0` | `0xaefd80` | 46 | stadium and created-field filename formats | `c48517d74bdc52bbc8239899780be7cd305a7fd8499cfdc153277e82c0ed9aae` |
| `0x001c7659` | `0x1b7659` | 123 | contact value through hold-onto-ball and Fumble slider tables to random test | `9d4ac61ca37834644e0050df6b9226862719f0d0696534c0d43cd7b4cdd9c178` |
| `0x001c5550` | `0x1b5550` | 34 | native probability random comparison | `8b1b19bada85bb0c74b1478cac19a632384678ff2674ab2400ec9537e3bee87e` |

# 25th Anniversary: more moments, the data contract (m1 engine, schema 1)

m2 writes human values; the engine (`mod_editor/core/nfl2k5_espn25_more_moments.py`, job m1) turns them into
records, strings, kits and team files. Reference tables (franchise asset codes, uniform indices with their era
labels and kit files, the 82 stadiums, the 75 retail historic files) are in
`/media/noah/Storage/.b76-research/m1/out/reference.json`. They are read from the user's retail roster and are not
committed.

## `data/nfl2k5_espn25_more_moments.json`

```json
{"schema": 1, "moments": [ {...}, ... ]}
```

The moments go in list order: the first becomes row 26. There are 25 at most, 50 rows in all. Each moment:

| Field | Value | Engine encoding (SITU record) |
| --- | --- | --- |
| `id` | unique text, for example `helmet_catch` | not stored |
| `title` | upper case, 27 characters or fewer (retail 9 to 27) | +0x00 string |
| `date` | `"February 3, 2008"` (retail style, 15 to 18 characters) | +0x0C string |
| `history` | 320 to 445 characters, plain ASCII, no em dashes | +0x04 string |
| `goal` | one sentence, 46 to 86 characters like retail | +0x08 string |
| `stadium_index` | 0 to 42, see reference.json (0 to 31 are the 2004 NFL parks, 31 = Reliant Stadium Houston; 35 to 40 are the future Super Bowl sites, 38 = "Super Bowl 2008", Tempe AZ). Every one has its nine day/afternoon/night and dry/rain/snow packages | +0x10 |
| `stadium` | the real venue's name at the time of the game, plain ASCII, 3 to 40 characters (optional). The details screen shows it in place of the stand-in record's name; the game keeps using the stadium at `stadium_index` for everything else (display only) | the owned code (venue table) |
| `stadium_note` | say when the index is a substitute | not stored |
| `away`, `home` | a `team_key` from teams.json | +0x14/+0x1C and +0x18/+0x20 (selector, season) |
| `user_side` | `"away"` or `"home"` | +0x24: 0 away, 1 home |
| `possession` | `"away"` or `"home"` | +0x28 |
| `score_now` | `{"away": n, "home": n}` | +0x2C, +0x34 |
| `final_score` | `{"away": n, "home": n}` | +0x30, +0x38 |
| `quarter` | 1 to 4 (5 = overtime; avoid unless the moment needs it, not yet proved) | +0x3C: quarter - 1 |
| `clock` | `"2:07"`, the real time left in the quarter, up to 15:00 (retail never exceeds 5:00; values above it are kept only once the offline setup proof passes, else the engine clamps and says so) | +0x4C, seconds as float |
| `down`, `distance` | down 1 to 4, yards to go. A kickoff start is down 0 with distance 10, `possession` = the kicking team and `ball_on` = the kicker's own 30 (the retail convention) | +0x48, +0x44 |
| `ball_on` | `"ATL 29"`: either team's abbreviation from teams.json and a yard line 1 to 50, or `"50"` | +0x40: home goal line = -50, away goal line = +50 |
| `timeouts` | `{"away": 0-3, "home": 0-3}` | +0x50, +0x54 |
| `weather` | `clear`, `light rain`, `heavy rain`, `flurries`, `heavy snow` | +0x60: 0 to 4 (the game's own list) |
| `time_of_day` | `day`, `afternoon`, `night` | +0x64: 0 to 2 |
| `temperature` | whole degrees F (the game makes rain at least 33 and snow at most 31) | +0x68 |
| `kits` | `{"away": K, "home": K}`; K is a uniform index 0 to 14 of that franchise (reference.json lists each index with its era label, for example Giants 2 = "1981 - 1999 Uniform", 0 = the 2004 uniform), or `{"era_year": 1985}` and the engine picks the index whose years cover it, else 0 | +0x58 away, +0x5C home |
| `sources` | URLs, or nflverse `game_id` / `play_id` | not stored |

The mini helmets on the list, the Controller Assign uniform label and the kit files all follow the franchise asset code
and the uniform index.

## `data/nfl2k5_espn25_more_teams/teams.json`

```json
{"schema": 1, "teams": {"giants_2007": {"selector": "giants", "season": 2007, "asset_code": "18",
                                         "nickname": "Giants", "city": "New York", "abbreviation": "NYG",
                                         "template": "h-18-2003-giants-0.iff", "retail_same_season": null}}}
```

- **`selector`** is the franchise's 2004 nickname in lower case (`49ers`, `bears`, ... `titans`; reference.json
  `franchises[].selector`). The engine matches it together with `season`.
- **`asset_code`** is that franchise's art code (reference.json). It picks the uniforms, helmets, playbook label and
  logos.
- **`abbreviation`** is the retail identity abbreviation (STL for the Rams, OAK, SD, ARZ, even for later seasons); `ball_on`
  uses it too. The engine writes each file's team record the retail historic way: nickname "Giants '07", abbreviation
  "NYG07", your era `city`. The scorebug abbreviation comes from the label the loader copies from the NFL team with
  the same asset code.
- **`template`** (optional) is the retail historic file whose team record (stadium, coach, uniform era table) the new
  file copies. The default is the franchise's retail file closest in season.
- **`retail_same_season`**: the retail file that already is this exact team-season, if one exists (for example THE
  MISS's `h-01-1998-falcons-1.iff`). The engine still writes a new file with your roster and leaves the retail file
  alone. The retail file only serves as the template.
- **Every team_key gets its own new file.** It uses one of the disc directory's free slots, shared with other jobs.
  Reuse a team_key across moments when it is the same team-season.

## `data/nfl2k5_espn25_more_teams/<team_key>.csv`

The columns are the same as `data/nfl2k5_espn25_moment_rosters/*.csv`
(`pool,index,first,last,position,jersey,college,` then the 28 ratings in `nfl2k5_roster_records.RATING_BYTE_ORDER`),
plus these:

| Column | Value |
| --- | --- |
| `pool` | `primary` |
| `index` | 0 to 52, row order |
| `first`, `last` | 15 characters or fewer each, the codec's name rules (`validate_name`) |
| `position` | QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE (the retail positions; the build reclassifies them when One-pool positions are on) |
| `depth` | 1-based order inside the position. For T G DE DT OLB ILB CB WR the engine maps 1, 2, 3, 4 ... onto the retail left/right chains: 1 = left starter, 2 = right starter, 3 = left second, and so on |
| `jersey` | 1 to 99, unique inside the team (document any exception) |
| `height`, `weight` | inches; pounds 150 to 405 |
| `birth_date` | `YYYY-MM-DD` |
| `years_pro` | 0 to 31 |
| `college` | exactly a name in the main college table, else empty (the template's is kept) |
| `hand` | `Left` or `Right` (empty = Right) |
| ratings | the 28 bytes, 0 to 99; `power_run_style` 1, 50 or 99; `kicking_style` as retail |

- **Row count.** Exactly 53 rows.
- **Position minimums.** At least 2 QB, 1 K, 1 P, 4 WR, 2 HB, 1 FB, 2 TE, 2 T, 2 G, 1 C, 2 DE, 2 DT, 3 linebackers
  (OLB + ILB), 3 CB, 1 FS and 1 SS.
- **Appearance.** Face, skin, gear and so on are copied from the template's player at the same position and depth,
  unless columns named as in `nfl2k5_espn25_scenarios.APPEARANCE` are present.
- **Announcer name calls.** When a player is also in the retail 2004 roster (same name and birth date), the engine
  reuses his announcer name call and photo.

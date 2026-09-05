# NFL 2K5 franchise save — the blocks beyond the roster arena

`mod_editor/core/nfl2k5_franchise_save.py` opens a franchise `SAVEGAME.DAT` (720,044 bytes), keeps
every byte, and gives typed access to the tables the game serialises after the roster arena.
`to_bytes()` of an untouched save is byte-identical to the input; writes go through the existing
`SaveContainer` (HMAC re-sign, never over the source).

```python
from mod_editor.core import nfl2k5_franchise_save as fs

save = fs.FranchiseSave.load("save_fixtures/256B40374FD6-Franchise1")   # EXTRA verified on load
save.one_line()          # '2011 (year field 7), offseason stage 1 week 0/1, user team(s) DET, cap $88.1M, ...'
save.header.display_year, save.user_teams(), save.salary_cap             # 2011, [18], 88113
save.games(rows=[0])     # week-1 grid cells: home/away/date/kickoff, quarter scores when played
save.coach_for_team(18)  # Steve Mariucci: W/L, Super Bowls, 23 ratings, formation tendencies
save.injured_reserve()   # [] or InjuredReserveEntry(team, slot, player_index, name)
save.place_on_injured_reserve(0, 1369)     # Finn's 17-byte IR move, reproduced byte for byte
save.set_salary_cap(90_000); save.set_display_year(2012)
save.write("out/Franchise1-edited")        # re-signed copy; the source is untouched
```

Every offset below is file-relative.  **PROVED** = the game's own load routine names the field or a
consumer was read and the real saves agree; **HYPOTHESIS** = layout proved, meaning inferred from
data; **OPAQUE** = carried verbatim, meaning unknown.  `REGIONS` in the module tiles the whole file
with these rows (`regions_cover_file()`), so nothing is silently unaccounted for.

## The four blocks

| offset | size | block | evidence |
|---|---|---|---|
| `0x00000` | `0x2E0` | settings prefix (RAM `0xE5FF80..0xE60260`, the 21 sliders) | `nfl2k5_save_writer` |
| `0x002E0` | `0x91040` | roster arena: `ROST` wrapper (declared `0x91020`), preamble `0x300` (version 0), object `0x320`, arena to `0x91320` | `nfl2k5_roster_records`, `nfl2k5_save_rost` |
| `0x91320` | `0x83DC` | **season block** — an image of RAM `0xE57776..` with pointers turned into indices, then the league stat tables, then an `0x80` tail | serialiser `0xC5310` (zeroes exactly `0x83DC` bytes when the sub-state is 3), restorer `FUN_000c5800`, `FUN_001349a0` |
| `0x996FC` | `0x165B0` | **front-office block** — orders, log, trades, FA bids, cap, boards, ledger, injured reserve, per-team blocks; its last table ends at `0xAFCAC` = end of file | `FUN_002d0ce0` (mode 2 only), `[ebp+offset]` reads in the disassembly |

The ROST serialiser/loader pair (`FUN_000c0730` / `FUN_000c0500`) is documented in
`save_rost_codec.md`; the season block is what the `FUN_000c5800` gap in the Ghidra ledger hid: the
serialiser at `0xC5310..0xC5800` was never made a function, which is why nobody found the callers.

## Season block (`S = 0x91320`)

| S+ | file | size | field | RAM | status |
|---|---|---|---|---|---|
| `0x00` | `0x91320` | 1 | mode, 2 = franchise | `DAT_00e576a0` | PROVED |
| `0x01` | `0x91321` | 1 | stage = row of the `.rdata` stage table at `0x515140`; rows 7/8/9 have 5/17/5 weeks = preseason / regular season / postseason, rows 0–6 are one-week offseason stages (labels live in `.bss`, unproved) | `DAT_00e576a4` | PROVED (weeks), names HYPOTHESIS |
| `0x02` | `0x91322` | 1 | sub-state; 3 makes the serialiser write an empty block | `DAT_00e576a8` | PROVED |
| `0x03` | `0x91323` | 1 | team count (32) | `DAT_00e576ac` | PROVED |
| `0x04` | `0x91324` | 1 | the stage's week count (17 in season) | `DAT_00e576b0` | PROVED |
| `0x05` | `0x91325` | 1 | week within the stage (0 in both real saves) | `DAT_00e576b4` | HYPOTHESIS |
| `0x06` | `0x91326` | 1 | year field; display year = 2004 + field (year 7→8 witnessed in game by the A7 lane) | `DAT_00e576b8` | PROVED |
| `0x08` | `0x91328` | 2 | u16 | `DAT_00e576bc` | OPAQUE |
| `0x0A` | `0x9132A` | 1 | flag | `DAT_00e576c8` | OPAQUE |
| `0x0B` | `0x9132B` | 12 | playoff seeds A — team indices, `0xFF` none (Franchise1: 12 seeds incl. DET) | `DAT_00e578f4` | PROVED |
| `0x17` | `0x91337` | 12 | playoff seeds B | `DAT_00e57924` | PROVED |
| `0x23` | `0x91343` | 1 | pad | — | OPAQUE |
| `0x24` | `0x91344` | 34×u32 | division 0..7 per team (seeding `FUN_002a7d60` reads it) | `DAT_00e576d4` | PROVED |
| `0xAC` | `0x913CC` | 34×u32 | user control per team; `FUN_000c4d70` takes the first non-zero as "the user team". Franchise1: only DET. Finn's 8007Fran: all 32 set | `DAT_00e5775c` | PROVED |
| `0x134` | `0x91454` | 34×u32 | per-team word (only DET non-zero in Franchise1) | `DAT_00e577e4` | OPAQUE |
| `0x1BC` | `0x914DC` | 34×u8 | team order: indices of the pointers at `DAT_00e5786c` (`0xFF` = null) | — | PROVED |
| `0x1DE` | `0x914FE` | 374×u16 | grid flags, two bytes per cell (`0x0101` on every filled cell) | `DAT_00e57954` | PROVED |
| `0x4CA` | `0x917EA` | 374×8 | the grid: 22 rows × 17 slots of `{type, home, away, month, day, code, hour, minute}`; type 0 scheduled, 3 played, 7 row end; rows 0–16 weeks, 17 wild card, 18 divisional, 19 conference, 20 Super Bowl, 21 Pro Bowl; team ids alphabetical by nickname, 32/33 = AFC/NFC | `DAT_00e57c40` | PROVED |
| `0x107A` | `0x9239A` | 374×10 | quarter scores, five bytes per side, written only for played cells (the probe's "unknown matrix") | `DAT_00e587f0` | PROVED (side order HYPOTHESIS: home first) |
| `0x1F16` | `0x93236` | 2 | pad | — | OPAQUE |
| `0x1F18` | `0x93238` | 17×5×28 | award records, two player indices each (`+4`, `+8`), converted from pointers; 17 weeks × 5 | `DAT_00e5968c` | HYPOTHESIS (players of the week) |
| `0x2864` | `0x93B84` | 306×u16 | | `DAT_00e59fd8` | OPAQUE |
| `0x2AC8` | `0x93DE8` | 4 | | `DAT_00e5a23c` | OPAQUE |
| `0x2ACC` | `0x93DEC` | 4 | one dword `FUN_001349a0` stores at its object `+0x2C50` | — | OPAQUE |
| `0x2AD0` | `0x93DF0` | 17×0x32C | league stat tables, one 812-byte row per … (17 rows; `FUN_001338c0/8f0/990` fix up 6+2, 3×3+4+2 references per row) | — | HYPOTHESIS (league leaders) |
| `0x60BC` | `0x973DC` | `0x22A0` | league stat tail (`FUN_001349a0`) | — | HYPOTHESIS |
| `0x835C` | `0x9967C` | `0x80` | tail (`FUN_00031000(0x80)`); zero in the 2004 save | — | OPAQUE |

## Seven-seed bracket and the two saved seed arrays

With `nfl2k5_playoffs14`, the twelve entries at season `+0x0B` remain
**AFC seeds 1–6 followed by NFC seeds 1–6**. They are not a fourteen-team field.
The other twelve-entry array at `+0x17` is separate: its first runtime dword,
`0xE57924` (`LAST7`), holds the seventh team from the **most recent** seeding
call. The next conference or a clinch calculation can overwrite it. Saving
that dword does not preserve two independent seventh seeds.

Both seventh seeds are instead durable in the ordinary saved game grid:
the away-team byte in wild-card slots **0 (AFC)** and **3 (NFC)**. For an
18-week patched season these bytes are at file `0x9217C` and `0x92194`;
for the 17-week layout they are at `0x920F4` and `0x9210C`. In general:
`0x917EA + 8 * (17 * wild_card_row + slot) + 2`.
The two #1 seeds occupy the home bytes of divisional slots 0 and 2. Other
wild-card home/away pairs encode seeds 2v7, 3v6, 4v5 in each conference.

PROVED: the patched builder at `0x2A7E57` writes these records; the advance
routine at `0x325E70` reconstructs the seed order from them. The dependent
`nfl2k5_playoff_picture` callbacks at `0x372BB0` / `0x372C60` read the same
saved grid and flags, deriving the wild-card row from `0x5151C4`. Bounded
instruction tests clear both seed arrays, restore grid/flags/scores, and
verify names, scores, and a forced seventh seed advancing after a mid-round
reload. This models the documented serialized fields; it does not claim an
in-game save/load observation. No save format or serializer changes are made.

## Front-office block (`F = 0x996FC`)

| F+ | file | size | field | RAM | status |
|---|---|---|---|---|---|
| `0x0000` | `0x996FC` | 14×32×u32 | fourteen per-team byte tables stored in dword slots; table 0 is a permutation of 0..31 in the year-7 save (identity in 2004) | `DAT_00e3c0b4 …` | HYPOTHESIS (table 0 = draft order) |
| `0x0700` | `0x99DFC` | 4 | | `DAT_00e3c0ac` | OPAQUE |
| `0x0704` | `0x99E00` | 4 | four bytes | `DAT_00e3c0a4/a8/b0`, `DAT_00e3c274` | OPAQUE |
| `0x0708` | `0x99E04` | 256×12 | log: `{u32 packed, u32 a, u32 b}`; kind = bits 7–12 (kinds 0x1A/0x1B/0x1C carry player indices in `a`/`b`) | `DAT_00e40588` | HYPOTHESIS (transactions / news) |
| `0x1308` | `0x9AA04` | 2 | log count (u16) | `DAT_00e41890` | PROVED |
| `0x130A` | `0x9AA06` | 1 | log flag | `DAT_00e41894` | OPAQUE |
| `0x130C` | `0x9AA08` | 32×8 | per-team player reference A `{u16 player, u16, u16, u16}` | `DAT_00e41898` | HYPOTHESIS |
| `0x140C` | `0x9AB08` | 32×8 | per-team player reference B | `DAT_00e41a18` | HYPOTHESIS |
| `0x150C` | `0x9AC08` | 32 | per-team byte | `DAT_00e41b98` | OPAQUE |
| `0x152C` | `0x9AC28` | 1 | flag | `DAT_00e41bd8` | OPAQUE |
| `0x1530` | `0x9AC2C` | 32×f32 | per-team float (2004: 103..320; year 7: −20..253) | `DAT_00e41bdc` | HYPOTHESIS |
| `0x15B0` | `0x9ACAC` | 32 | per-team rank 1..32 (DET = 1 in the year-7 save) | `DAT_00e41c5c` | HYPOTHESIS (standings rank) |
| `0x15D0` | `0x9ACCC` | u32 | **salary cap**, $1000 units: 80,500 (2004) and 88,113 = 80,500 × 1.013⁷ (year 7) | `DAT_00e3c278` | PROVED |
| `0x15D4` | `0x9ACD0` | 15×34 | trade records (`FUN_002d06d0`: kind byte, two team bytes, 2 × 3 player indices, value words) | `DAT_00e3c27c` (60-byte) | PROVED layout |
| `0x17D2` | `0x9AECE` | 100×12 | free-agent bid slots (`FUN_002d05b0`: player index, team byte, bid words) | `DAT_00e3c600` | PROVED layout |
| `0x1C82` | `0x9B37E` | 32×36×4 | per-team boards `{u16 player, u8 value, u8}` (all empty in both saves) | `DAT_00e3cc40` | HYPOTHESIS |
| `0x2E82` | `0x9C57E` | 1 | byte | `DAT_00e3f060` | OPAQUE |
| `0x2E83` | `0x9C57F` | 32 | team permutation (same as table 0 in year 7; `0xFF` in 2004) | `DAT_00e41bb8` | HYPOTHESIS |
| `0x2EA3` | `0x9C59F` | 1 | pad | — | OPAQUE |
| `0x2EA4` | `0x9C5A0` | 32×36 | per-team record: seven f32 0.5 + two dwords | `DAT_00e41ce0` | HYPOTHESIS (AI weights) |
| `0x3324` | `0x9CA20` | 8 | eight bytes before the ledger count | — | OPAQUE |
| `0x332C` | `0x9CA28` | u32 | ledger count (552 in year 7) | `DAT_00e3f06c` | PROVED |
| `0x3330` | `0x9CA2C` | 600×12 | ledger `{u32 packed, u16 player, u16, u8 team, pad}` | `DAT_00e3f070` | HYPOTHESIS (franchise history) |
| `0x4F50` | `0x9E64C` | 32×u32 | per-team dword (~53.6 M in both saves) | `DAT_00e42160` | OPAQUE |
| `0x4FD0` | `0x9E6CC` | 32×5×4 | **injured reserve**: `{u16 primary player index, u16 pad}`, `0xFFFF` empty; index → record via `FUN_002d0540` | `DAT_00e421e0` | PROVED |
| `0x5250` | `0x9E94C` | 32×2000 | per-team blocks (constant `00 00 00 01` fill in both saves) | `DAT_00e42460` | OPAQUE |
| `0x14C50` | `0xAE34C` | 32×u32 | | `DAT_00e3d210` | OPAQUE |
| `0x14CD0` | `0xAE3CC` | 32×u32 | (random-looking words) | `DAT_00e3d290` | OPAQUE |
| `0x14D50` | `0xAE44C` | 32×65×3 | three bytes per roster slot (zero in both saves) | `DAT_00e51f60` | OPAQUE |

## Franchise fields inside the arena

* **Coach record** (`0xA8` bytes; table at root `+0x30/+0x34`, 35 on retail; team `+0x14C` points at
  one): `+0x00/+0x04` first/last name, `+0x08/+0x0C/+0x10` three info lines, `+0x18` body (u32),
  `+0x1C` seasons with team, `+0x1E` total seasons, `+0x20/+0x22/+0x24` career W/L/T, `+0x26/+0x28/+0x2A`
  season W/L/T (promoted at rollover by `FUN_00247b40`), `+0x30` winning seasons, `+0x32` Super Bowls,
  `+0x34/+0x36` playoff W/L, `+0x38/+0x3A` Super Bowl W/L, `+0x40` photo id, `+0x42..+0x58` the 23
  ratings, `+0x59` play-calling run %, `+0x83..+0x8C` formation run/pass tendencies.  Finn's map,
  re-checked: Belichick reads 75–69, 2 Super Bowls, 7–1 in the playoffs entering 2004 — his real
  numbers.  PROVED.
* **Team salary** `team+0x124` (u32, $1000): recomputed by `FUN_000c3f00` = Σ contract values of players
  with a remaining term + the IR charge (`FUN_00246f20`).  PROVED.
* **Team record ring** `team+0x19C..+0x1A8` (7 × u16): `FUN_0013ed30(team, slot)` adds a value to a slot,
  `FUN_0013ed70` shifts the ring down at rollover.  Location PROVED, slot meaning HYPOTHESIS.
* **Team season stats** `team+0x1AA..+0x1E8` (u16 each), `+0x1DC` games played (`FUN_00134dd0`); the stat id
  merged into each field is in `TEAM_STAT_FIELDS`; ids `0x4C` passing yards, `0x50` rushing yards,
  `0x62` total yards, `0x42` turnovers are named from the per-game descriptor table (`.data 0xAE59C0`).
  PROVED (ids), labels for the other 27 ids still to be read off the runtime string table.
* **Season template** root `+0x28/+0x2C` → 256 games at `0x72A94` (type 0), the schedule the game copies
  into the grid at season start (`FRANCHISE_2026_SCHEDULE`).  PROVED.

## Writers and what they change

| call | bytes touched | status |
|---|---|---|
| `set_year_field` / `set_display_year` | `0x91326` | witnessed in game (A7) |
| `set_user_control(team, flag)` | `0x913CC + 4·team` | unwitnessed |
| `set_game(row, slot, …)` | one 8-byte grid cell (played cells refused unless `allow_played`) | unwitnessed |
| `set_salary_cap` | `0x9ACCC` | unwitnessed (Finn's editor writes the same dword) |
| `place_on_injured_reserve(team, player)` | team pointer list compacted, team `+0x11C` −1, player `+0x28` = `0xEE`, IR slot | reproduces Finn's move byte for byte; his moves load in game |
| `activate_from_injured_reserve` | the inverse (player re-added at the end of the list) | unwitnessed |
| `set_coach_field` | one coach field / rating / tendency | unwitnessed |
| `set_team_record_ring` | one u16 | unwitnessed |

## Not done

The runtime string table (`.bss`) that names stages, stat ids and log kinds is not in the XBE, so those
labels need a memory dump or an in-game read.  The 17-row league stat tables, the 600-record ledger,
the 32 × 2000-byte team blocks and the per-team floats are carried verbatim.  Player season/career stat
cells live in the arena's history pool (`nfl2k5_roster_records`), not here.

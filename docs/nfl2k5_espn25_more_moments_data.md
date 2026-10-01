# 25th Anniversary: 25 more moments, the data (job m2)

EXPERIMENTAL / UNWITNESSED. Sourced data and a documented ratings model for the m1 engine
(`mod_editor/core/nfl2k5_espn25_more_moments.py`, whose own contract is `docs/nfl2k5_espn25_more_moments_contract.md`
on m1's branch). Nobody has played these moments; no claim here is a lab or Noah witness.

Labels: PROVED OFFLINE (read from the source data or checked by a test), DESIGN (a choice made here), INFERRED
(reasoned, not tested).

## Files

| File | What |
| --- | --- |
| `data/nfl2k5_espn25_more_moments.json` | `{"schema": 1, "moments": [...]}`, rows 26 to 50 in list order |
| `data/nfl2k5_espn25_more_teams/teams.json` | one record per team-season (`giants_2007` ...) |
| `data/nfl2k5_espn25_more_teams/<team_key>.csv` | 53 players per team-season |
| `data/nfl2k5_espn25_more_teams/manifest.json` | per-player provenance, input hashes, CSV hashes |
| `data/nfl2k5_ratings_reference.json` | the retail 2004 rating scale the ratings model maps onto |
| `tools/nfl2k5_espn25_more_moments_spec.json` | the hand-written half: texts, the chosen plays, stadiums, kits, sources |
| `data/nfl2k5_ratings_forty_sources.json` | hand-curated input: cited 40-yard times (page and quote) for players the nflverse combine file lacks, and the players searched without a result |
| `tools/nfl2k5_espn25_more_moments_build.py` | the generator; `--check` regenerates in temporary storage and compares every byte |
| `mod_editor/core/nfl2k5_ratings_model.py` | the ratings model (`docs/nfl2k5_ratings_model.md`) |

Inputs that are never committed: nflverse-data release files (CC-BY-4.0, nflverse contributors), downloaded
unchanged (`play_by_play_<season>.csv.gz`, `roster_<season>.csv`, `roster_weekly_<season>.csv`,
`depth_charts_<season>.csv`, `stats_player_reg_<season>.csv.gz`, `snap_counts_<season>.csv`, `combine.csv`,
`players.csv`; hashes in the manifest), and the user's retail ESPN NFL 2K5 (USA) game (the 2004 main roster and the
75 historic files).

## `nfl2k5_espn25_more_moments.json`

Field names follow m1's contract. Per moment:

- `id`, `title` (upper case, 27 characters or fewer), `date` ("February 3, 2008"), `history` (320 to 445 characters),
  `goal` (46 to 86 characters): plain ASCII, facts only, no long dashes.
- `stadium` (the real venue), `stadium_index` (0 to 42, the retail stadium list), `stadium_note` (why that index).
- `away`, `home`: team keys. The official home/away designation of the real game (for a Super Bowl, the designated
  home team).
- `user_side`, `possession`: "away" or "home".
- `score_now`, `final_score`, `timeouts`: `{"away": n, "home": n}`.
- `quarter` (1 to 4; no moment starts in overtime), `clock` (the real time left in the quarter, "8:31"; m1 proved
  the scenario setup stores values above 5:00 as given), `down` (1 to 4; 0 is a kickoff), `distance`, `ball_on`
  ("NYG 17" with the retail identity abbreviation, or "50").
- `weather` (clear, light rain, heavy rain, flurries, heavy snow), `time_of_day` (day, afternoon, night),
  `temperature` (degrees F).
- `kits`: `{"away": K, "home": K}`, a uniform index of the franchise (the notes say when it is a stand-in).
- `sources` (URLs, and the nflverse game_id and play_id), `evidence`, and `notes` where needed.

### How a situation is read (PROVED OFFLINE)

From nflverse play-by-play, at the chosen start play: the offense (`posteam`; on a kickoff the kicking team), the
score before the play (`posteam_score`, `defteam_score`), quarter, clock, down, distance and yard line, and the
timeouts left before the play (the previous row's `home/away_timeouts_remaining`; 3 each at a half's first play).
The final score is the game's. Weather and temperature come from the play-by-play (`roof`, `weather`, `temp`); a
dome or closed roof is "clear" at 70. The time of day is the start play's own wall-clock time (`time_of_day`, UTC)
in the venue's standard time: from 17:00 night, from 14:00 afternoon, else day. THE MISS (1998) has no nflverse
play-by-play; its situation is written in the spec with its sources, and its timeouts (3 and 3) are INFERRED.

## Team-seasons

`teams.json` per team key: `selector` (the franchise's 2004 nickname in lower case), `season`, `asset_code`,
`nickname`, `city` (era-correct), `abbreviation` (the retail identity abbreviation, for example STL for the Rams),
`template` (the franchise's retail historic file closest in season), `retail_same_season` (the retail file that is
this exact team-season, or null). m1 writes a new file for every team key and never changes a retail file.

### The 53 players (DESIGN, each step recorded per player in the manifest)

1. **The pool.** The week of the moment's game: nflverse weekly roster, status ACT and INA (the 53-man roster, no
   practice squad). Before 2002 there are no weekly rosters: the season roster's active players. Every player the
   game's play-by-play names for the team, and every featured player in the spec, is added if missing.
2. **Positions and depth.** That week's nflverse depth chart: the listed slot (LT, RDE, SLB, NCB, ...) gives the
   2K5 position and side; generic slots (LB, S, DB) use the player's own roster position. For 1998 the starting
   lineup comes from the cited game article. Players not on the chart use their roster position.
3. **Exactly 53.** Extra players are dropped from those who neither took part in the game nor sit on the chart,
   inactive before active, least season production first; short rosters are filled from the season roster.
4. **Minimums.** m1's (2 QB, 1 K, 1 P, 4 WR, 2 HB, 1 FB, 2 TE, 2 T, 2 G, 1 C, 2 DE, 2 DT, 3 LB, 3 CB, 1 FS, 1 SS)
   plus 2 ILB and 2 OLB, so both 4-3 and 3-4 playbooks find starters. A short position borrows the most suitable
   player from a related one (a team without a fullback uses its heaviest spare back or tight end), recorded as a
   role fill.
5. **Depth order.** 1-based inside each position. Sided positions (T G DE DT OLB ILB CB WR): left starter, right
   starter, left second, right second (m1 maps this onto the retail chains). Players listed at the same rank with no
   side (three WRs, two safeties) are ordered by season production.
6. **Numbers.** The number the game's own play-by-play prints for the player ("85-D.Tyree"), else the weekly
   roster's, else another week of the same season. Numbers are unique inside a team. Four players have no usable
   number in any source (missing, a 0, which old files use for a missing value, or one a teammate wears): Samuel Womack (49ers 2023),
   Jimmy Farris (Patriots 2001), Nicholas Grigsby (Patriots 2017) and Raymond Perryman (Raiders 2001) get a free
   number, marked `invented_free_number` in the manifest.
7. **Names.** nflverse full name, ASCII, 15 characters or fewer (a longer hyphenated name keeps its first part and
   the next initial, recorded). The spec's `display_names` map gives the name a player went by where nflverse has a
   legal name or other capitalization (Gabe Davis, NaVorro Bowman, Ike Taylor).
8. **Physicals.** Height, weight, birth date, years in the league from the roster row; college only when it is
   exactly a name in the retail college table.
9. **Hand.** Left for the left-handed quarterbacks of the spec's cited list, and for players the retail 2004 roster
   marks left-handed (quarterbacks, kickers and punters); else Right.
10. **Ratings.** A team-season that a retail historic file already is keeps 2K's own ratings (six team-seasons:
    the 1998 Falcons and Vikings, 1999 Titans, 2001 and 2003 Patriots, 2003 Panthers), carried by player: the slot
    named after him, else the placeholder slot with his jersey number, else the strongest open slot of his position,
    else of his position family, else a copy of the weakest slot of his position; never a slot of another family.
    Every other team is rated by the ratings model on that season's statistics, with the retail 2004 ratings of a
    player 2K5 already had as his anchor (`retail_identity` in the manifest: `exact` name and birth date; `loose`, a
    name unique in the retail rosters with the same position family and a birth year within three, since 2K's
    birth dates are sometimes wrong; `alias`, the same last name, exact birth date and position family under another
    first name, as 2K's Edward Reed).
11. **Speed.** Per player, the manifest's `ratings_basis.speed_source` says where speed came from: `retail_anchor`,
    `combine` (nflverse), `cited_combine`, `pro_day` or `other_40` (a cited time from
    `data/nfl2k5_ratings_forty_sources.json`, with `forty_source`), or `profile` (flagged `speed_flag`: searched, no
    usable time). Every WR, CB, safety, back and edge rusher on the profile is listed in the sources file with a
    null time and the reason. Per team, `speed_sources` counts them.

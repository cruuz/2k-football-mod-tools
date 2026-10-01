# Real-player ratings on NFL 2K5's scale (`mod_editor/core/nfl2k5_ratings_model.py`)

Job m2, 2026-09-23 (model `m2-ratings-3`). DESIGN / PROVED OFFLINE: a documented model from real statistics, not 2K's own ratings. Nobody
has played with these ratings. Reusable for any season (job u1 feeds 2025 statistics with 2026 roster rows).

## The idea

A player who was the league's best at his position in his season should get the ratings 2K5 gave the best player at
that position in its 2004 rosters; a mid-pack starter the ratings of a mid-pack 2004 starter; a backup who never
played the ratings of a 2004 backup. So the model turns real production into a percentile inside the league at the
player's 2K5 position, and reads 2K5's own scale at that percentile.

## Steps

1. **Position.** Each row carries one of the 17 retail positions. `map_position(position, depth_chart_position,
   weight)` maps an nflverse row: the specific position when there is one (LT to T, NT to DT, MLB to ILB, SLB to
   OLB, NCB to CB, EDGE to DE); generic codes by weight (OL: T from 315 lb, else G; DL: DT from 295 lb, else DE; S:
   SS from 208 lb, else FS; DB: CB under 200 lb, FS under 208, else SS; LB: OLB; LS: C).
2. **Production** for the season (nflverse `stats_player_reg_<season>`), plus `starts` (weeks listed first on the
   nflverse depth chart; both the 2001-2024 weekly schema and the 2025 snapshot schema are read) and `snaps` (the
   sum of per-game snap shares, 2012 on). One value score per position, plus aspects:

   | Position | Value | Aspects (and the ratings they drive) |
   | --- | --- | --- |
   | QB | pass EPA + rush EPA + 0.15 x (attempts + carries) | accuracy: completion rate (pass_accuracy); arm: air yards per attempt, else yards per attempt (pass_arm_strength); read: EPA per dropback (pass_read_coverage); mobility: rushing yards per game among QBs with 50+ attempts in 4+ games (scramble). Composure, consistency, leadership follow the value |
   | HB, FB | scrimmage yards + 20 x TD + 5 x catches - 40 x fumbles lost + 25 x snaps + 3 x starts | receiving (catch, run_route); ball security, fumbles lost per touch, lower is better (hold_onto_ball); value (break_tackle; FB run_blocking) |
   | WR, TE | receiving yards + 20 x TD + 5 x catches + rushing yards - 40 x fumbles lost + 25 x snaps + 3 x starts | hands: catches per target (catch); value (run_route, hold_onto_ball; TE blocking) |
   | T, G, C | 10 x starts + 17 x snaps | value (run_blocking, pass_blocking) |
   | DE, DT | rush + 0.5 x stop + 3 x forced fumbles + 2 x passes defensed + 6 x TD + 2 x starts + 20 x snaps | rush = 4 x sacks + 1.5 x QB hits (pass_rush); stop = tackles + 1.5 x tackles for loss (tackle, run_coverage) |
   | OLB, ILB | stop + 0.75 x rush + cover + 3 x FF + 6 x TD + 2 x starts + 20 x snaps | stop (tackle, run_coverage); cover = 4 x INT + 2 x PD (coverage); rush (pass_rush) |
   | CB, FS, SS | cover + (0.5 CB, 0.8 S) x stop + 3 x FF + 2 x sacks + 6 x TD + 2 x starts + 20 x snaps | cover = 5 x INT + 3 x PD (coverage); stop (tackle; safeties run_coverage); ball = INT (catch) |
   | K | 3 x FG + 1 per 40-49 make + 2 per 50+ make - 2 x misses + 0.5 x PAT - 2 x PAT misses | accuracy: FG rate (kick_accuracy); power: longest make + 4 per 50+ make (kick_power) |
   | P | 0.5 x punts + 4 x (gross average - 40), scaled by volume | power: gross average (kick_power); placement: inside-20 rate (kick_accuracy) |

   Tackles count solo plus half of the assisted ones.
3. **Percentiles.** The population is every player at that 2K5 position in the season: the season roster (active,
   reserve, inactive; no practice squad or cut players) plus anyone with statistics. A player's value percentile is
   his rank in that population (ties share the middle). A backup who never played sits at the bottom, as in a real
   depth chart.
   - Rate aspects are shrunk toward the league's volume-weighted rate (QB 150 attempts, HB 60 touches, WR 40
     targets, TE 30, K 12 attempts, P 30 punts of league-average performance added), ranked among qualified players
     (QB 150 attempts, HB 60 touches, FB 20, WR 30 targets, TE 20, K 10 attempts, P 30 punts), and then move the
     player's value percentile in logit space: logit(q) + strength x volume trust x (aspect rank - 0.5), strength 2
     for accuracy, reading, hands and K accuracy, 1.5 for ball security, K power and punting, 1 for arm strength
     (air yards per attempt is largely a scheme number). In the middle of the league that is about plus or minus
     0.23; near the top it compresses, so the best passers are told apart instead of all reaching 2K5's ceiling. A
     starter with a poor completion rate is still rated as a starter, just a less accurate one.
   - Count aspects (sacks, tackles, interceptions) are averaged with the value percentile.
   - A starter (a `depth` within the position's starters per team: QB 1, WR 2, T 2, G 2, C 1, DE 2, DT 2, OLB 2,
     ILB 1, CB 2, FS 1, SS 1, HB 1, FB 1, TE 1, K 1, P 1) rates at least like the league's weakest regular starter at
     his position that season: the value percentile of rank 32 x starters. A player who started the moment's game
     after a partial regular season (Nick Foles, Super Bowl LII) plays like a starter.
   - Linemen in a season with no starts or snaps data (before 2001): 0.72 for a starter, 0.35 for the next two,
     0.2 below. A rookie with no statistics gets a draft prior (first round 0.55, second 0.42, rounds three and
     four 0.32, later 0.2) instead of the bottom. Optional honors floor the value percentile (AP first team 0.97,
     second team 0.94, Pro Bowl 0.9).
4. **The 2K5 scale** (`data/nfl2k5_ratings_reference.json`, built from the user's retail 2004 rosters of the 32 clubs,
   1,696 players, when the data is generated):
   - `quantiles[position][rating]`: that rating's own distribution at 41 percentile points. The driven skill
     ratings above take the value at the aspect's percentile, so the league's best passer gets the accuracy of
     2K5's best passer.
   - `profile[position][rating]`: the retail players ranked by the studio's documented OVR estimate
     (`nfl2k5_roster_records.OVERALL_WEIGHTS`), kernel-averaged (bandwidth 0.05) at each percentile. Every rating
     that no aspect drives comes from the profile at the value percentile.
5. **Measurables.** 2K5's speed follows the combine 40-yard time: speed = 315.1 - 50.7 x forty (r = -0.949,
   residual SD 5.0, 794 retail players matched by exact name to the nflverse combine file, PROVED OFFLINE when the
   reference is built). A player's speed comes from the first of these that exists (recorded as `speed_source` in
   the basis):
   1. `retail_anchor`: he is also in the retail 2004 rosters (the caller passes his retail ratings as `anchors`).
      He keeps his own retail speed, agility, strength and jumping, minus 1 speed and agility per year of age past
      30, and his retail scramble value (magnitude and throwing-animation parity); his arm strength (QB) or leg (K,
      P) is half his retail rating and half this season's model value.
   2. `combine`: his nflverse combine 40, joined by pfr id, else by name and draft year when exactly one player in
      `players.csv` matches (the name key ignores case, punctuation, spaces and Jr./III, so "LeKevin Smith" meets
      "Le Kevin Smith").
   3. A cited 40 from the caller's `forty_sources` file (`nfl2k5.forty_sources.v1`, keyed by gsis id, each with its
      page and quote; `data/nfl2k5_ratings_forty_sources.json` holds the m2 team-seasons): `cited_combine` (a
      combine time the nflverse file lacks, for example before 2000), `pro_day`, then `other_40` (a cited time whose
      event the source does not name). Each maps onto the scale exactly like a combine time.
   4. `profile`: the position profile at his value percentile, flagged `speed_flag` in the basis.
6. **Style bytes**, retail's own conventions read off the 2004 rosters: kicking style 99 for K, 1 for P, 49 else;
   power-run style 1/50/99 for HB by weight (208 lb or less Finesse, 228 lb or more Power), for WR (186 or less,
   212 or more), 1 for defensive backs, 50 for QB/K/P, 99 for everyone else; scramble 5 for non-quarterbacks, and
   for a quarterback an even value from 20 to 96 by his mobility percentile (2K's own value for a retail QB).

## API

```python
from mod_editor.core import nfl2k5_ratings_model as rm
stats = rm.SeasonStats.from_files(2025, "stats_player_reg_2025.csv", "roster_2025.csv",
                                  depth_charts="depth_charts_2025.csv", snap_counts="snap_counts_2025.csv",
                                  combine="combine.csv", players="players.csv",
                                  forty_sources="my_forty_sources.json")   # optional
rows = rm.rate_players(rows, stats, rm.Reference.load(), honors=None, anchors=None)
```

`rows` are dicts with at least `position` (a 2K5 code) and `gsis_id` (empty = no statistics); `weight`,
`birth_date`, `years_pro`, `draft_number` and `depth` are used when present. Each output row adds the 28 rating
columns (`nfl2k5_roster_records.RATING_BYTE_ORDER`) and `rating_basis` (JSON: percentiles, anchor, priors, and
`speed_source` with `forty`, `forty_source` or `speed_flag`).

Cited 40s: `SeasonStats.from_files(..., forty_sources=rm.DEFAULT_FORTY_SOURCES)` (a path or a mapping;
`rm.load_forty_sources` validates it: a time from 4.1 to 6.2 s, a kind in `rm.FORTY_KINDS`, a `source_url` and a
`quote`; entries without a time only record a search and are skipped). A combine time from nflverse always wins over
a cited one.
`rate_player(row, stats, reference, honors=None, anchor=None)` rates one row and returns `(ratings, basis)`.

CLI: `python -m mod_editor.core.nfl2k5_ratings_model rate --roster team.csv --season 2025 --stats
stats_player_reg_2025.csv --population roster_2025.csv [--depth-charts ...] [--snap-counts ...] [--combine ...]
[--players ...] [--forty-sources ...] --out rated.csv`.

## Limits (INFERRED unless marked)

- Offensive linemen are separated only by starts, snaps and optional honors; statistics say nothing about blocking.
- Pro-day times are mapped like combine times, as main asked; pro days are often hand-timed on faster surfaces, so
  a pro-day speed may run a point or two high (INFERRED). "Other" times name no event.
- Next Gen Stats top speeds are not used: there is no published per-player table for these seasons (tracking data
  is public only from 2016, and only per play in articles). DESIGN.
- Regular-season statistics only: a player's postseason form does not count (Eli Manning's 2007 playoff run does not
  lift his 2007 ratings).
- The OVR estimate that orders the retail profile is the studio's, not the game's own formula.
- Tests: `tests/mod_editor/test_nfl2k5_ratings_model.py` (synthetic league, both depth-chart schemas, the CLI, and a
  real 2007 check when the private downloads exist).

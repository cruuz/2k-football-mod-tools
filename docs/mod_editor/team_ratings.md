# Dynamic modern team ratings

`team_ratings: true` in a Studio build recipe installs modern OFFENSE, DEFENSE and
OVERALL getters. The Advanced and Experimental presets enable it; Basic does
not. It requires `position_pools: true`. The pass runs after the final roster
refresh and draft ownership pass. It adds one 288-byte read-only allocation and
replaces three existing routines in place. There are no new runtime dependencies,
team-specific ratings, roster edits, or changed player-overall formulas.

The model is deliberately tied to the current roster. Every query walks the
native roster with `C4400`, aggregates with `C45A0`, and obtains each player's
position-specific floating overall from `246D80`. Both native rank and side
orders matter. A player is a starter when the smaller order is below the row's
threshold. Starters have weight 1 and other players weight 0.10 within their
position pool. The thresholds select QB1, HB1, WR1/2/3, TE1, C1, G1/2, T1/2,
EDGE1/2, DT1/2, LB1/2, CB1/2/3, FS1 and SS1. Custom duplicate depth orders retain
native behavior and can select more players; this patch does not repair a corrupt
depth chart. Empty required positions contribute zero.

| Unit | Position weights |
|---|---|
| OFF | QB 30, HB 10, WR 20, TE 10, C 6, G 12, T 12 |
| Optional FB/H-back | Add 2 to both weight and denominator only when enum 8 exists |
| DEF | EDGE 30, DT 20, LB 10, CB 25, FS 7.5, SS 7.5 |
| OVR | Equal mean of OFF and DEF |

An H-back stored in enum 8 receives the optional FB contribution. An H-back
stored as TE receives the TE contribution. Renaming the slot has no effect.
Removing enum 8 does not leave dead weight in the denominator. Legacy OLB enum
10 is not an EDGE pool; modern rosters must be reclassified. The required modern
chain mapping makes 3-4 and 4-3 views give identical ratings for identical
personnel. This is a nickel evaluation, not a base-defense lineup selector.
Special teams retain their separate native rating. They no longer skew OVR.

The previous model uses the same live roster walkers, not saved team ratings.
Each 20-byte row is `{u16 weight, u8 threshold, s8 position, getter, bench, lo, hi}`.
For each position, it computes a depth-weighted mean of `(attribute-lo)/(hi-lo)`.
An empty pool yields zero but keeps its row weight. `C45A0` averages rows;
`C4650` maps the result using `clamp(.45 + .55*(x-.70)/(.91-.70), .45, 1)`.

`C4830` averages offense A (`4F1520`, 10 rows) and B (`4F15E8`, 9 rows).
A weights sum to 375: QB 90, C 20, G 40, T 50, FB 15, TE 30, WR 120, HB 10.
B weights sum to 240: QB 15, C 20, G 50, T 40, HB 80, FB 20, WR 5, TE 10.
These weight different attributes, not player overalls. Exact getter, bench,
and normalization values are transcribed in the tr1 native evidence.

`C4860` averages defense A (`4F16A0`, 16 rows) and B (`4F17E0`, 9 rows),
then multiplies by 40/23 and subtracts 0.72913045. A has weight 185: EDGE 40,
DT 20, LB 45, CB 30, FS 25, SS 25. B has weight 225: EDGE 50, DT 40, LB 100,
CB 5, FS 10, SS 20. The pre-existing pool patch already redirects old OLB rows
to LB and counts three starting off-ball linebackers. This prevents the empty
OLB collapse, but still double-weights that merged pool in multiple attribute
rows and leaves nickel CB3 at bench weight.

`C48A0` also calls special teams (`C4810`, table `4F1894`). If OFF > DEF,
OVR is `(3*OFF + 2*DEF + .5*ST + .3)/5.5`; otherwise it is
`(2*OFF + 3.5*DEF + .5*ST + .3)/6`. The branch favors the stronger unit.
The new equal mean removes that nonlinear advantage.

The displayed number is multiplied by 100, capped at 100 and truncated. The
existing letter-grade formatter uses 95 A+, 90 A, 85 B+, 80 B, 75 C+, 70 C,
65 D+, 60 D, 55 F+, 50 F, otherwise F-. Its scale is unchanged.

The direct reference census on the base executable finds:

| Getter | Direct CALL/JMP sites |
|---|---|
| OFF C4830 | 5837B, C48A6, 1CF37A, 1CF38B, 218CE0, 31F22C |
| DEF C4860 | 583B7, C48B1, 218D10, 31F23D, 34BB60 |
| OVR C48A0 | 584E6, D23E0, D23EB, 1062BF, 1062D3, 115C03, 31F24E |

`31F1D0` computes the team-select/controller panel values into transient UI
buffers; its formatter at `31F6C2` produces the letters. `218CE0/218D10` are
stat wrappers, `34BB60` the overall-defense list getter, `1061F0` uses OVR in
simulation, and `1CF370` uses OFF in gameplay. `58330` is a seven-way strength
helper: after enough season games its branches can use team statistics instead
of roster ratings. Those statistics are not rewritten. Separate pass/rush
ratings and weekly-prep subratings still use the original specialized getters.

There is no refresh hook to add after a trade, signing or rollover: these three
getters read current records every time their existing callers ask. This also
means changing OVR affects native simulation consumers, not just UI text.
The evidence proves the getters, current roster changes, scheme flags and
formatter; it does not establish every transitive screen path, completed trade
UI flow, full-season rollover, or the resulting simulation balance.

Calibration uses [NFL Stats team metrics](https://stats.innerpulse.net/teams),
2026 through Week 5, retrieved October 14. Use the raw offensive EPA/play,
negative defensive EPA/play allowed, and their difference, not the site's
inconsistent headline/table power columns. The site attributes EPA to nflverse /
nflfastR. The frozen numeric evidence is `metrics.json` in the tr1 handoff.

We searched 38 football-shaped offensive and 16 defensive candidates. Offensive
QB weights were 25/30/35/40, WR 20/25/30, HB and TE 5/10, with OL constrained to
20..35 and shared equally per lineman. Defensive EDGE and CB were 25/30/35,
LB 10/15/20, safeties 7.5 each, and remaining DT weight constrained to 10..20.
For each candidate, a linear regression predicting EPA was trained on 31 teams
and tested on the held-out team, repeated for all 32. The lowest mean squared
prediction error chose the weights above. Only weights are installed, not the
fitted regression coefficients. Equal OFF/DEF OVR was chosen for transparency.

Spearman correlations, with average ranks for ties, were OFF .3401 -> .5353,
DEF .4014 -> .4201 and OVR .2766 -> .3696 on the refreshed ro1 roster. Because
candidate selection used this same 32-team cohort, these are descriptive results,
not an independent generalization claim. Five weeks of EPA and inherited player
ratings remain imperfect measures of real strength. No team-specific offsets
were fitted to hide disagreements.

Tests run real x86 under Unicorn, with no substituted rating/player leaves.
The 32 teams match independently aggregated native pools; all 96 panel strings
use the actual installed formatter. Tests also cover absent FB, TE reclassification,
WR3/CB3 depth changes, roster-attribute changes, scheme independence, foreign
bytes, replay, existing allocation preservation and Studio/repair equality.
The repair tool supports full-disc virtual comparison when a disc copy is not
permitted. XBE write/replay is physically verified separately.

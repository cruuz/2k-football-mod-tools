# Dynamic display team ratings

`team_ratings: true` installs modern OFFENSE, DEFENSE and OVERALL for the
team-select/controller panel and the overall-defense spreadsheet column.
Advanced and Experimental enable it; Basic does not. Modern position pools
must be installed or requested. The pass follows final roster and draft-pick
writers. It allocates 512 executable bytes and 512 read-only bytes, then redirects
four existing five-byte UI CALL instructions. The three native getters and all
14 simulation/AI caller instructions keep their exact original bytes.

Raw display scores are computed from the current roster on every query, using
native C4400/C45A0 and floating player-overall getter 246D80. No team-specific
scores or offsets are stored. A player's smaller rank/side order determines
starter eligibility. Starters have weight 1 and bench players weight .10.
The evaluated personnel are QB1, HB1, WR1/2/3, TE1, C1, G1/2, T1/2, EDGE1/2,
DT1/2, LB1/2, CB1/2/3, FS1 and SS1. Identical personnel receive identical display
scores under either 3-4 or 4-3. Empty required positions contribute zero.

| Unit | Position weights |
|---|---|
| Raw OFF | QB 30, HB 10, WR 20, TE 10, C 6, G 12, T 12 |
| Optional FB/H-back | Add 2 to numerator weight and denominator only if enum 8 exists |
| Raw DEF | EDGE 30, DT 20, LB 10, CB 25, FS 7.5, SS 7.5 |
| Raw OVR | Equal mean of raw OFF and raw DEF |

An enum-8 H-back receives optional FB weight; a TE H-back participates in TE.
Labels do not affect the calculation. Retired OLB enum 10 must be reclassified
by the existing modern-pool roster pass. Custom duplicate depth orders retain
native behavior; this feature does not repair corrupt depth charts.

## Display spread

The unscaled modern scores compressed OVR to 74.3..83.9. Each unit now has a
fixed, strictly increasing piecewise-linear curve. Five interior anchors map
min/Q1/median/Q3/max of the accepted refreshed 2026 roster's raw scores to the
same quantiles of the pinned USA retail roster's native scores. Quantiles use
linear interpolation at `(n-1)*q`. Endpoints (0,0) and (1,1) complete each curve;
inputs outside 0..1 are clamped. The knots are stored as float32 pairs.

Curves stay fixed during a franchise. A changed player rating or depth order
immediately changes the score along that curve. There is no live league rerank,
so improving another team cannot lower this team's display rating. Raw OVR is
mapped independently, rather than averaging mapped OFF and DEF, which preserves
the accepted OVR rank order. All three continuous rank orders are verified for
all 32 current clubs. Integer and letter displays naturally introduce ties.

The resulting ranges are OFF 72.06..95.51, DEF 71.64..96.71 and OVR 76.71..93.87.
OVR letters change from C:2/C+:21/B:9 to C+:4/B:11/B+:11/A:6. The target retail
OVR distribution is C+:4/B:8/B+:15/A:5. Matching quartiles gives a similar spread,
not an exact forced allocation of letter grades. The EPA rank correlations are
unchanged by this monotonic display mapping.

## Simulation and AI isolation

The release uses display-only routing. No better simulation outcomes have been
proved, so the native numerical formulas and their consumers remain intact.
The audit scans all XBE sections for direct CALL/JMP and absolute references to
C4830, C4860 and C48A0. It finds 18 direct references and no absolute pointers.
Every site is classified below. All four redirected instructions are CALLs.

| Site | Native getter | Classification and route |
|---|---|---|
| `05837B` | `0C4830` | AI: shared team-strength comparator; retain native |
| `0583B7` | `0C4860` | AI: shared team-strength comparator; retain native |
| `0584E6` | `0C48A0` | AI: shared team-strength comparator; retain native |
| `0C48A6` | `0C4830` | AI: native overall dependency; retain native |
| `0C48B1` | `0C4860` | AI: native overall dependency; retain native |
| `0D23E0` | `0C48A0` | simulation: matchup-strength predicate; retain native |
| `0D23EB` | `0C48A0` | simulation: matchup-strength predicate; retain native |
| `1062BF` | `0C48A0` | simulation: match initialization; retain native |
| `1062D3` | `0C48A0` | simulation: match initialization; retain native |
| `115C03` | `0C48A0` | AI: league record/strength selection; retain native |
| `1CF37A` | `0C4830` | simulation: live-game initialization; retain native |
| `1CF38B` | `0C4830` | simulation: live-game initialization; retain native |
| `218CE0` | `0C4830` | AI: trade unit-strength evaluation; retain native |
| `218D10` | `0C4860` | AI: trade unit-strength evaluation; retain native |
| `31F22C` | `0C4830` | UI: team-select/controller panel; display owner |
| `31F23D` | `0C4860` | UI: team-select/controller panel; display owner |
| `31F24E` | `0C48A0` | UI: team-select/controller panel; display owner |
| `34BB60` | `0C4860` | UI: overall-defense spreadsheet column; display owner |

The team panel writes transient display arrays; the spreadsheet getter supplies
the overall-defense column's cell value. Specialized pass/rush columns retain
their existing formulas. 218CE0/218D10 were incorrectly described as display
wrappers in the first report. Their sole references are function arguments at
218FE5/21901C to 218D30, which ranks roster strength for trade evaluation and
stores decision fields C11A34/C11A38. They remain native.

58330 is a shared team-strength comparator that can switch from roster ratings
to season statistics. It remains native. D23C0 compares the two selected teams'
OVR and returns a boolean matchup predicate; it is logic, not a rating renderer.
115B50 selects a league team using record and `(1-OVR)`, storing the selected
identity and score at league +5808/+580C. Its exact award/event label is not
established, so it is conservatively classified as outcome-selection logic and
kept native. The sim initializer 1061F0 and live-game initializer 1CF370 also
retain their native calls. Internal calls from native OVR stay native.

The native proof executes every actual CALL/JMP edge and its real callee for
all 32 teams, stopping before the rest of each caller body. All 448 non-UI cases
match the baseline exactly; all 128 UI cases return the new display scores.
Separately, native getter bytes, non-UI instruction bytes and all 96 direct native
getter results match the baseline. The display getters leave no persistent shared game-state changes. The native
OL-overall helper temporarily substitutes player byte +2A and restores it;
the native test verifies that only those bytes, stack locals and the probe
output are written, and the full shared arena is identical afterward. This proves routing and formula
preservation, not complete season simulations or improved sim balance.

The first unreleased d1eb870e binary replaced native getter bodies. This revision
refuses it and requires rebuilding from the original base. It does not embed
retail bytes to restore those overwritten routines. A clean base receives the
new display owner directly. Existing allocations keep their addresses and bytes.

## Native formulas retained for logic

The native formula, retained for simulation and AI, uses the same live roster walkers, not saved team ratings.
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
The raw display OVR uses an equal mean before its own spread mapping.

The displayed number is multiplied by 100, capped at 100 and truncated. The
existing letter-grade formatter uses 95 A+, 90 A, 85 B+, 80 B, 75 C+, 70 C,
65 D+, 60 D, 55 F+, 50 F, otherwise F-. Its scale is unchanged.

## Raw-score calibration

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

Tests run actual x86 under Unicorn with no substituted rating/player leaves.
They verify weighted raw pools, all mapped scores, all caller edges, the full
reference census, all 96 panel strings through the real formatter, scheme
neutrality, optional FB, WR3/CB3 depth changes, native release and attribute
changes, monotonic mapping across more than 3,000 samples, no persistent shared state
changes, native code/result preservation, foreign-byte refusal, replay, allocation
preservation and Studio/repair equality. Physical XBE write/replay and a complete
virtual-disc scope scan are recorded in the private handoff. No new runtime
library is required.

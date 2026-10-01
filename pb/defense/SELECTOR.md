# PROVED OFFLINE: retail defensive selector and fixture boundary

PROVED OFFLINE: The executable pin is SHA-256 `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`. [selector.py](selector.py) maps its original executable bytes under Unicorn, relocates the PLAY header plus play names and chain pointers, initializes the retail opcode table pointer `0xBE4E20 = 0x521078`, and runs `0x1A9840` and `0x1A9A80` on every play. Invalid plays fail; usable bits are set by native validation. No xemu, Xbox execution or executable patch is involved.

| PROVED OFFLINE address | PROVED OFFLINE role exercised |
| --- | --- |
| `0x20B820` | Native orchestration: category, formation, front, coverage, result tuple |
| `0x208480` | Opponent category and field-position mapping; selected branches use down |
| `0x20A240`, `0x2081B0` | Formation lookup, category membership, compatibility, available front and coverage, candidate scoring/lottery |
| `0x20A7F0` | Usable compatible front candidates |
| `0x20AA40` | Compatible coverage candidates for the selected front and formation |
| `0xE1440` | Native play/formation compatibility |
| `0x208820` | Native score path with neutral 54-float profile |
| `0x203F20` | Donor header curve and matchup multiplier |
| `0x203440` | Weighted lottery: formation score exponent 1, front/coverage exponent 3 |
| `0x48B50`, `0x48B90` | Native RNG with reproducible fixture state |
| `0xE1320`, `0xE1360`, `0xACCE0` | Separate native menu walks and page construction for the hang regression |

PROVED OFFLINE: Header bits 9-11 index a five-point curve at `0x50AFE0`: 0 -> 2, 1 -> 1.4, 2 -> 1, 3 -> 0.5, 4 -> 0.1, clamped thereafter by the native interpolator. The pair score multiplies both curves. The `0x04000000` front flag multiplies by 0.8; `0x00010000` on either component multiplies by `1 - (matchup * 0.15 - 0.6)`. The fixture's matchup 0.5 gives 1.525. `0x281580` also reads a game-plan state; the fixture's zero/default state yields 1. Custom v2 defenses may change only score bits 9-11; family, compatibility and all other donor bits remain exact. Preset recipes retain their entire header. The donor signature and original header are checked against the source. These discrete score bands are not percentage fields. Cubing makes menu counts alone an inadequate rate prediction.

PROVED OFFLINE: The fitter uses score band 2, or band 3 on pressure-tagged donors to offset their neutral matchup multiplier, when allocating unique coverage records in each ordinary formation. A native extraction then reads actual candidate pointers and float scores immediately before the lottery, enumerates every front/coverage pair, and computes its normalized probability. The extraction refuses 30-candidate overflow rather than approximating the retail replacement rule. A separate regression compares the model's cubic probabilities against 12,000 executions of the original lottery and checks native validation rejects a corrupted permission bit.

DESIGN: The state sweep uses four downs, distances 2/7/15, seven field locations 1/5/20/50/80/95/99 yards from the attacking goal, and three offensive category codes 0/6/8. Each of 252 state rows per team executes native `0x208480`. Repeated categories reuse the native candidate distribution under the fixed fixture. One full `0x20B820` witness per distinct category must select a member of that enumerated distribution. The state grid is uniformly weighted and does not replay the real 2025 opponent snap mix. Summary percentages are exact conditional expectations under the model, not finite-sample gameplay observations. All ordinary-formation calls form the comparison denominator; retail goal-line selections are retained in the state/selection receipts and excluded from the DC-rate comparison.

DESIGN: Explicit fixtures replace these providers:

- `0x20B400`: requested category resolved to an exact or next eligible category record. The full game-plan/situational provider is not initialized.
- `0x207EF0`: formation matchup score fixed at 1.
- `0x205660`: player matchup fixed at 0.5.
- `0x1889C0`, `0x2045F0`: mirror predicates false.
- `0x208420`: prevent predicate false in the main comparison; separately exercised as a true fixture in regression.
- `0x204AB0`: postselection bookkeeping omitted because the harness reads the explicit output tuple.

DESIGN: Distance is recorded but does not alter this fixture's weights. Full `0x20B400` down/distance policy, nonzero 54-float profiles, roster matchup grids, play history, clock/score adjustments, formation reuse and live RNG startup distribution remain unproved. Consequently the table cannot establish that a real CPU game reaches the same percentages. Nickel/dime selection is driven by offensive category and game state, so measured personnel rates are not promised through coverage menu editing.

DESIGN: Man/zone and split-family labels in the rate model describe authored intent. The real data's single/split coverage families are post-snap proxies. Neither is an observed pre-snap shell. Actual two-high rates remain NA instead of substituting Cover 4 counts or inventing tracking data. Modern match exchanges start some defenders in man; they are kept in their intended zone family, explicitly separating mixed assignment mechanics from a charting claim.

PROVED OFFLINE: Receipts include source hashes, candidate pairs, per-pair rush/deep checks, 252 state rows per team, native selected tuples and aggregated rates. [sweep.py](sweep.py) reproduces them from the small compiled resources created by [verify.py](verify.py). DESIGN: Main's lab is still required for live fronts, shells, pressure, assignment exchanges and stall freedom.

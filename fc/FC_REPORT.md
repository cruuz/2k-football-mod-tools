# PROVED OFFLINE: fc phase 3, economy and practice-squad composition

PROVED OFFLINE: this phase starts at integrated stack `13fdc3250b48` on `job/b76-fc3`. The two owners previously disagreed over the six bytes at `0x322BB0`. The combined form now passes both owners' inspection, applies identically in either order and supports exact selective reverts. [Composition receipt](proof/phase3_composition.json).

| Area | Evidence | Phase 3 result |
|---|---|---|
| Shared entry | PROVED OFFLINE | `0x322BB0` enters the existing practice-squad CPU guard. Its allowed continuation at `0x3d161f` jumps to the existing economy gate at `0x31e605`. |
| Native behavior | PROVED OFFLINE | 13 Unicorn cases pass without substituted game routines. Both guards, native signing, minimum quotes, cap budgeting, FA removal, roster append and transaction logging execute. |
| Install and revert | PROVED OFFLINE | Both install orders are identical, both owners report applied, reapplication changes zero bytes, either owner can be removed while retaining the other, and both revert orders restore the exact retail executable. |
| Full recipe | PROVED OFFLINE | FULL candidate B with economy and the fc roster completed on September 27. Both owners report applied on the final XBE; selective reapply is byte-exact and all 13 native fill cases pass. The verified disc was deleted. [Full proof](proof/phase3_full_build.json), [every owner](proof/PHASE3_OWNER_STATUS.md). |
| Route repair | PROVED OFFLINE | The main menu wraps. Replaced the repeated-UP row guess with vb2's recorded fresh-menu MyNFL route. Syntax checked only; no xemu execution. |
| Finance representation | DESIGN | Phase 2's fitted-contract, original APY/cash, future schedule and historical dead-money limitations still apply. This phase fixes patch composition, not those accounting limits. |

## DESIGN: ownership and execution

DESIGN: the canonical flow is `0x322BB0 -> cpu_sign_guard -> economy_fill_gate -> 0x322BB6`. The practice-squad guard saves/restores all general registers around its existing `ps_room` check. A refusal returns zero with `ret 16` before the economy or native signing body. An allowed call jumps from the old 11-byte displaced-prologue continuation to the economy gate, padded to the same extent. The economy gate checks the 54-player bound and clamps the input budget to cap room less its existing rounding reserve, then performs `sub esp,0x114` once and resumes the retail body. The stricter practice-squad season limit remains 53; the economy's existing off-season bound remains 54.

PROVED OFFLINE: entry bytes are `e95bea0a0090`; continuation bytes are `e9e1cff4ff909090909090`. The shared gate adds no executable allocation, save field or on-disc size increase. The standalone entry forms are unchanged. The full-build table correction below regenerates the rookie routine and moves its data. The two-owner executable SHA-256 is `05341edb6293eb2964e36c2d7d979ab51a5b0a998ee1f79aee42bef53b166944`.

DESIGN: [the shared composition owner](../mod_editor/core/nfl2k5_roster_fill_composition.py) supplies inspection projections only after validating the full supporting owner. Missing dependencies, changed branch bytes, damaged continuations and partial owners fail closed. Projection respects the existing arena-growth delegation and validates section digests through that path. Applying either second owner selects the same canonical bytes and recomputes all touched section digests.

DESIGN: both modules now expose `revert(payload, retail)`. Revert requires the complete hash-pinned USA retail reference, restores only that owner's spans, reconnects the surviving owner and repins touched sections. It preserves unrelated edits. The practice-squad owner refuses removal while arena growth still depends on it. The economy can be removed while retaining arena growth and practice squads.

PROVED OFFLINE: [reservation revalidation](proof/phase3_manifest.json) observes both standalone applications and both install orders. It retains the parent manifest's historical disc evidence, adds the newly observed economy/shared reservations and full owner capacities, and updates the four changed writer/template fingerprints plus the new shared helper. This is a bounded owner revalidation, not a claim of regenerating the parent's disc build.

## PROVED OFFLINE: additional full-recipe composition fixes

PROVED OFFLINE: the [first FULL build](proof/phase3_first_full_build_failure.json) prepared all 5,886 project entries and passed executable patching with economy and practice squads. It then refused Franchise Edit Player. The economy had reused `0x52157c` as a 252-byte rookie-knot table, but the first seven words are also the last seven live predicates in the native 600-byte Player Contracts action table. The native pick evaluator indexes past those words for round one. This was a real economy ownership bug, not a reason to relax the editor's guard.

DESIGN: the rookie table now starts at `0x521598`, uses 224 bytes, and ends at the same `0x521678` boundary. The generated rookie routine targets that address. All 600 Contracts action bytes remain retail, and Franchise Edit Player remains unchanged. Tests cover both installation orders, exact output equality, inspection and replay.

DESIGN: the broader allocator-stack check also found MyCareer's guarded franchise initializer includes the economy's initial-cap instruction at `0x13ef17`. MyCareer now validates the complete economy owner before normalizing that exact instruction in its private hash view. Every other initializer byte remains guarded. Tests reject a lone cap instruction and a damaged economy body.

## PROVED OFFLINE: native CPU fill proof

PROVED OFFLINE: [the native receipt](proof/phase3_native_fill.json) records all 13 cases, budgets, payroll, cap, counts, ABI checks and visited native routines. [Reproduction tool](../tools/franchise_economy/composition_probe.py). The fixture initializes the native roster and franchise and uses real retail records with explicitly synthetic cap/roster boundaries. A low-rated rookie FA isolates the already-sourced minimum calculation. No game routine is stubbed.

| Boundary | Evidence | Result |
|---|---|---|
| Season roster at 53; physical 53 plus 12 reserves; invalid reserve metadata; null team | PROVED OFFLINE | Practice-squad guard refuses before the economy gate. |
| Off-season roster at 54; no cap room; zero budget | PROVED OFFLINE | Economy gate refuses before the retail signing body. |
| Budget below or exactly equal to the minimum quote; cap-room boundary after rounding reserve | PROVED OFFLINE | Both gates preserve the native strict affordability comparison; no signing. |
| Minimum quote plus one; sufficient cap room; season 52 active plus one reserve | PROVED OFFLINE | Native signing succeeds, one FA leaves the list, one player joins the active roster, payroll remains within cap and a native transaction is logged. |
| Every refusal and return | PROVED OFFLINE | The complete synthetic roster arena is unchanged on refusals; callee-saved registers and the `ret 16` stack ABI are preserved on all paths. |

DESIGN: this is bounded native CPU-fill proof. It does not extend phase 2's isolated season result to the whole candidate-B recipe, prove every CPU transaction route, or claim game rendering, save-device I/O or exact NFL accounting.

## PROVED OFFLINE: optional MyNFL route repair

PROVED OFFLINE: `/media/noah/Storage/.b76-research/vb1/tools/vb1_lab.py:open_mycareer` documents the wrapping list and fresh PLAY NOW selection. `/media/noah/Storage/.b76-research/vb2/runs/run4/cmds.txt`, Phase 2, records `DOWN, A, A`, the Start/continue/team-selection sequence, then Coach's Desk and Practice Squad. Its `screens/q00-desk.txt` contains Coach's Desk, Practice Squad and Front Office; `q01-practice-squad.txt` contains the active Giants list. These existing lab artifacts were read, not rerun.

DESIGN: [lab_route.py](../tools/franchise_economy/lab_route.py) now uses that entry sequence and waits for Coach's Desk/Practice Squad before continuing. Its finance/trade continuation remains unwitnessed and fails with an explicit miss if OCR cannot confirm a selection. Main still runs and reviews the lab. No xemu was launched in this phase.

## PROVED OFFLINE: full candidate-B build, validation and delivery

DESIGN: the copied recipe differs in exactly one override, `franchise_economy: false -> true`. Its inherited prose still describes the source recipe's economy-off history. The build explicitly uses the frozen merged roster with fc contracts, rather than the economy-off roster named in that historical recipe. The project and roster are byte-identical copies under `/media/noah/Storage/.b76-research/fc/astra-build/phase3/`; their hashes and zero-log roster replay are in the composition receipt. Pending options are not promoted into overrides.

PROVED OFFLINE: on September 27, the saved log hashes, input hashes, manifest source hashes and all 324 unified-provider pins matched. The exact 142 tests passed again with no skips in 466.175 seconds; the separate 13-case native receipt matched the saved receipt exactly. All saved task files remained unchanged through the FULL build. The interrupted September 25 log remains in `phase3/build.log`; the resumed log is `phase3/build_resume.log`.

PROVED OFFLINE: one resumed FULL build succeeded under `nice -n 10 taskset -c 0-23`, reusing the existing `phase3/.nfl2k5-compile-cache` through the builder's normal key and digest checks. Initial preflight took 698 seconds; the builder recorded 4,268 seconds for the build. All 5,886 project entries were prepared. The builder summary reports 93 applied options, zero not applied, two expected foreign states and eight summary inspection gaps. [Every owner and gap is reviewed here](proof/PHASE3_OWNER_STATUS.md). Seven gaps match nested settings inspections; the watermark value is recorded in its application receipt. Static scorebug and custom depth-role inspectors retain their documented foreign states. Disabled owners' foreign/unknown/unavailable observations are retained without a compatibility claim.

PROVED OFFLINE: one authored visual asset stayed retail: `00A0:arm_digit:6` could not fit its 944-byte slot after 21 fit attempts, with a recorded shortfall of at least one byte. Both 32-team playbook sets were applied and all 37 final books passed the builder's native scoring checks. The depth-role step reports its 248 refused groups explicitly. This is not a claim that every authored asset or requested role transformation was installed.

PROVED OFFLINE: the final disc was 6,090,037,248 bytes, SHA-256 `89001042f7cd41289b57840d5c1bddde2f0abd4e1a9b6abd555ef33add700563`; its final XBE SHA-256 was `b9b8d8f2bdf849043ef1a054eaec1ceaddca94dbd91a04a4b9eac3be9813681d`. The finisher independently confirmed both owners applied, reverted and reapplied each owner with exact final-XBE equality, ran all 13 native fill cases on that XBE, matched the disc hash to the builder receipt, and deleted the disc. The first finisher invocation exposed an incorrect reader reference before reading the disc; it now uses the existing `mod_build._xbe_bytes` reader. No native writer or build input changed after the build.

PROVED OFFLINE: the runner sampled free space every 15 seconds. Minimum observed NVMe space was 107,458,736,128 bytes, above 100 GiB; minimum Storage space was 18,094,776,320 bytes during staging. All build output stayed under `phase3/`. A transient Timeshift mount blocked two monitoring commands; the running build continued and shell access recovered without intervention. No xemu was launched. Final proof remains offline: full-season behavior, rendering, save-device I/O and the phase 2 accounting limitations remain outside this composition result.

PROVED OFFLINE: 142 final tests passed: 83 economy, squad, composition and editor tests; 58 MyCareer build/routes, provider and build tests; and one source-drift manifest test. The complete allocator stack also applies and replays with economy and practice squads. All 13 native fill cases were rerun after the table move. The generator reproduces the corrected template, all 324 provider source pins match, and route/finisher syntax and `git diff --check` pass. [Validation receipt](proof/phase3_validation.json). No skipped test is counted as a pass. The native fill proof substitutes no game routine; the existing editor menu fixture separately documents its service substitutions.

DESIGN: shared git metadata is read-only under this task's permission profile. Delivery therefore uses `.scratch/fc3.git`, an explicit pathspec commit based on `13fdc3250b48`, and `.scratch/fc-phase3.bundle`, with the required Astra co-author trailer. No push or tags.

---

# DESIGN: fc phase 2, real contract data and real-dollar display

## DESIGN: one-page summary for Noah

DESIGN: **This is a reviewable experiment, not a release of exact 2026 NFL finances.** The missing data is imported and the currency formatter now shows real units. A native contract record still cannot hold both an arbitrary cap schedule and the original cash/APY. Keep the option off the presets. Do not present the fitted contract figures as the player's actual deal.

| Area | Evidence | Result |
|---|---|---|
| Current data | PROVED OFFLINE | Used Main's September 24 nflverse parquet and lossless JSON. Both SHA-256 hashes are verified and pinned. The stale 2022 CSV was not used. |
| Coverage | PROVED OFFLINE | 1,695/1,696 active-contract matches (99.941%). 1,437 observed annual schedules, 259 explicitly modeled schedules, zero unresolved entries. |
| Missing schedules | DESIGN | 209 drafted rookies use OTC draft-slot estimates; 50 others use a one-year CBA minimum target, rounded to native units. These are rules, not invented signed contracts. |
| Replay | PROVED OFFLINE | All 1,696 contract-only edits replay on the frozen u7 names roster with zero log lines. No names, ratings, positions or membership are authored by fc. |
| Dollars on screen | PROVED OFFLINE | One guarded formatter serves 51 direct native calls. Cap text is `301.20m`; contract, trade, negotiation, card, re-sign and free-agent callbacks all use real units. |
| Allen trade-off | PROVED OFFLINE | Source deal: $330M over six years, APY $55M. Native text: fitted remaining total `325.36m`, current cap `44.24m`, generated demand `65.07m`. The $55M formatter vector is not an Allen APY result. |
| Annual accuracy | PROVED OFFLINE | Opening cap-fit error is at most $20,000/player. Later errors can be large: Mahomes's 2027 fit is $41,825,892 below source. Original histories and errors are retained. |
| Roster/cap gate | PROVED OFFLINE | All 32 teams pass at start, rollover and after free agency. IR returns are reconciled through native cuts; CPU signings check room and copy all new offer terms. The native gate is retained. |
| OTC comparison | PROVED OFFLINE | All 32 teams have published 2026 references beside native start/rollover finances. Native legacy dead money is zero; carryover, adjustments and OTC roster scope differ. This is not an exact OTC reproduction. |
| Lab | DESIGN | Main-only script composes the real fragment, writes native money dumps and builds on Storage. Live screen layout, clipping, save/load and final-disc behavior remain unwitnessed here. |
| Release decision | DESIGN | Unit conversion is consistent in the proven native call graph. Exact APY/cash, irregular future liabilities and real legacy dead money require a larger persistent contract model. This handoff stops short of release approval. |

## PROVED OFFLINE: inputs, matching and receipt

PROVED OFFLINE: phase 2 starts at `9ce0787e5605f3e2f8caaa921c970ef42a69595a` on `job/b76-fc`. The pinned USA XBE is `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`. The source files stay on Storage. No xemu, disc build, push, tags or other-worktree edits ran in this phase.

| Input | Evidence | SHA-256 |
|---|---|---|
| `historical_contracts.parquet` | PROVED OFFLINE | `0c13b84878e2a2d4aa1845bb5bf94ff2092f8bf646a5e2a570af94e8cb626418` |
| Main's lossless `historical_contracts.json` | PROVED OFFLINE | `eee20a3664e4c11d17cc4f7e51aa718ddc64b1e5692a1460475d78c51973d038` |
| Frozen u7 names edits | PROVED OFFLINE | `0b7ff8aacb5f71d1f29a8727d1af2e8b056d1a26bb4b2a687778620721ffe8c2` |
| r1 v2.4 ratings edits | PROVED OFFLINE | `754409ee5c2f4241e39c3c97f24e10b668365afafeec6cecc5bba7a35a49d0fb` |

PROVED OFFLINE: the [nflverse release asset](https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet) has the supplied asset time `2026-09-24T12:40:52Z`, 52,944 rows and 2,471 active rows. Money is converted from millions with decimal arithmetic. The importer refuses changed input hashes, incorrect conversion metadata and a JSON conversion without its matching parquet. [Importer](../tools/franchise_economy/import_contracts.py), [full receipt and ledger](data/contract_audit.json).

PROVED OFFLINE: the [NFL's 2026 cap announcement](https://www.nfl.com/news/2026-nfl-free-agency-questions-answers) supplies $301.2M, compared with [$279.2M in 2025](https://www.nfl.com/news/nfl-sets-salary-cap-at-279-2-million-per-team-for-2025-season). Those are league caps before club carryover and adjustments; the repeated future growth ratio is a DESIGN assumption.

DESIGN: matching tries GSIS ID, then OTC ID, then exact normalized name. Normalization removes punctuation, accents and suffixes; no fuzzy match is accepted. The supplied roster has no universal external-ID field, so IDs come from r1's identity table and the reviewed overrides. The resulting active matches use 1,591 GSIS IDs and 104 normalized names; this input did not require the OTC fallback. One player, Zach Ertz, has no active contract in the pinned release.

PROVED OFFLINE: [the reviewed identity list](data/identity_review.json) resolves 15 cases: Tyrel Dodson, Chris/Christopher Brooks, Sedrick Van Pran/Van Pran-Granger, both Byron Murphys, both Justin Jeffersons, Michael/Mike Reid, Michael Carter II, both Byron Youngs, DeVonta Smith, Brandon Crenshaw/Crenshaw-Dickson, Marcus Harris and Easton Mascarenas/Mascarenas-Arnold. Club and position separate duplicate names. Dodson has two active rows with the same IDs and no current annual history; both candidates are recorded, the rostered-veteran rule supplies his schedule. The source page links are provenance; the pinned snapshot controls the import.

PROVED OFFLINE: the [per-team match-rate CSV](proof/contract_match_rates.csv) distinguishes active matches from observed annual schedules. Every team has 53/53 active matches except Philadelphia at 52/53 (98.113%). All 32 have 53/53 resolved records after the explicit rules. Observed schedule coverage ranges from 41 to 49 players/team. The audit's zero-log replay writes only 8,480 values across the five contract fields, with zero moves.

DESIGN: only continuous positive playable schedules beginning in 2026 enter the fit. Cash-zero/void accounting years are excluded from playable term length but retained in `season_history_2026_and_later` and `excluded_years`. Duplicate or discontinuous positive schedules stop the importer for review. Every imported row retains its source contract history, headline cash/APY/guarantees, current-and-future annual history, fitted fields and annual errors.

PROVED OFFLINE: supplied spot checks agree with the snapshot: Josh Allen, Bills, 2025, six years, $330M, $55M APY; Jaxson Dart, Giants, 2025, four years, $16,977,942; Aaron Rodgers, Steelers, 2026, one year, $22.5M. Allen's playable source caps for 2026 through 2030 are $44.228M, $56.148M, $62.364M, $89.189M and $82.840M. His separate 2031 cash-zero $21.7M cap entry remains in the source ledger and is not another playable year.

DESIGN: the 259 missing annual schedules are explicitly marked `modeled`, even when an active headline deal exists. For 209 drafted 2026 rookies, interpolate the four annual caps between the 42 complete [OTC draft-estimate knots](https://overthecap.com/draft) retained in the phase 1 source file. Slots beyond the final observed knot, 253, use that knot and record both the actual and clamped slot. This is an estimate, not a reconstruction of a signed rookie deal.

DESIGN: the other 50 records receive one year at the experience-bracket minimum target: 46 undrafted rookies, Tyrel Dodson, Scott Daly, Darius Slayton and Zach Ertz. Incomplete three-year UDFA headlines do not establish annual cap schedules and are not silently treated as observed terms. Native `years_pro` proxies CBA credited seasons (INFERRED). The [CBA, Article 26](https://nflpaweb.blob.core.windows.net/website/PDFs/CBA/March-15-2020-NFL-NFLPA-Collective-Bargaining-Agreement-Final-Executed-Copy.pdf) supplies 2026 targets of $885,000, $1,005,000, $1,075,000, $1,145,000, $1,215,000 for years four through six, and $1,300,000 for seven or more. Native quantization can put the represented target below the exact minimum; this is not complete CBA enforcement.

## PROVED OFFLINE: central money formatter and actual text

PROVED OFFLINE: the shared native money formatter is `0x31E580`, with a guarded 198-byte replacement window. Its fastcall inputs are a signed amount in game thousands and a UTF-16 output buffer. The replacement multiplies by four only at this display boundary, handles negatives, clamps overflow, and calls the original wide-string formatter. Accounting, total-value storage, cap comparisons and save units remain internally scaled. Foreign or partially patched bytes are refused atomically; reapplying a complete patch is idempotent.

PROVED OFFLINE: a byte-reference census finds 51 direct calls in the pinned XBE, no tail jumps and no absolute pointer references to this formatter. [The complete addresses](proof/money_strings.json) are reproducibly checked by [money_probe.py](../tools/franchise_economy/money_probe.py). Native screen-family callbacks were executed with zero substituted leaves. An unrelated `$%d` template at `EA7094`, called by `32E653` and `32E99A`, is trivia score text and is intentionally unchanged.

| Native output | Evidence | Callback and text |
|---|---|---|
| Cap | PROVED OFFLINE | `366410`: `301.20m`; payroll/space use `366440`/`366460`. |
| Contract summary | PROVED OFFLINE | `21C000`: `5 years / 325.36m + 65.06m bonus` for Allen's fitted remaining record. |
| Trade list | PROVED OFFLINE | `2B9CC0`: `44.24m` current cap; `2B9D40`: `325.36m` fitted total; `2B9DA0`: `65.06m` modeled penalty. |
| Re-sign / free-agent list | PROVED OFFLINE | `3624D0`: `31.23m` base charge; `3624F0`: `65.07m` generated demand. |
| Negotiation schedule | PROVED OFFLINE | `347740`: `31.23m` base; `347790`: `13.01m` amortized bonus. |
| Player card | PROVED OFFLINE | Text branch `3474C8..3474F3`: `Salary : 325.36m`. This native label refers to total value. |

PROVED OFFLINE: [the exact text dump](proof/money_strings.txt) and JSON pin the composed roster and patched executable. Retail formatting truncates to hundredths of millions, so displayed `44.24m` represents an internal $44.248M. The isolated formatter vector `13750 -> 55.00m` proves units only. It does not prove that Allen's native record has $55M APY.

DESIGN: no proven native finance caller remains on the old display scale. Indirect computation of an address, external UI scripts, final menu navigation and renderer clipping are not established by the static reference census or text callbacks. The player-card probe executes its text branch and stops before the renderer-owned epilogue. Real hardware evidence must come from Main's lab. This is not a claim of every live screen being visually verified.

## DESIGN: representation trade-off and release stop

PROVED OFFLINE: the native 84-byte player record has a u16 total at `+0x0A` in game $10,000, remaining years in `+0x24`, curve and bonus tier in `+0x26`, and length in `+0x27`. Eight curves and eight bonus tiers cannot independently represent original cash, APY, guarantees, irregular annual cap hits and void-year accounting. The importer now allows up to 15 continuous years, the term nibble's capacity; an actual eight-year schedule is checked against the native salary routines.

DESIGN: each real dollar is divided by four internally. Total-value steps are $40,000 real and annual accounting steps $4,000. The opening-priority fit minimizes future errors subject to an opening error within five game-thousands where possible. All imported opening errors are within $20,000. Fitted bonuses are curve parameters, not the actual guaranteed or signing-bonus dollars. [Largest errors and every fallback](proof/fit_review.json).

PROVED OFFLINE: Allen's record stores 8,134 total units, five remaining years, curve 6 and bonus tier 2. That produces caps of $44.248M, $54.660M, $65.072M, $75.480M and $85.892M. The source original $55M APY exists only in the separate audit. Mahomes's eight-year record has a maximum later-year error of $41.826M. Formatting these numbers with real units cannot correct the lost information.

DESIGN: a faithful current-NFL release needs independent persistent annual liabilities, original APY/cash and guarantees, identity-linked display access, and void-year and release/trade accounting. It also needs an import of team opening dead money/carryover and appropriate CPU accounting; those team values are not inherently impossible to represent, but this experiment has not implemented them. Adding an APY string alone would make screens disagree with the accounting. I stopped short of that release claim and did not enable the option in any preset. The fragment and code are delivered for review and the explicitly labeled lab experiment.

DESIGN: the retained cap-growth scenario repeats `301.2 / 279.2`, not an official 2027 prediction. Native integer rounding makes the next cap $324.932M. Market valuation, generated balanced veteran contracts, fitted four-year rookie deals, draft-pick trade values, penalty saturation and user-control gating remain the phase 1 design. A saturated dead-money ledger blocks room rather than wrapping. Top-51 rules, exact options, tags, restricted rights and comprehensive CBA minimum enforcement remain outside this model.

## PROVED OFFLINE: retained accounting and trade census

| Location | Evidence | Native meaning |
|---|---|---|
| `E3C278`, u32 | PROVED OFFLINE | League cap in internal game thousands; startup patch writes 75,300. |
| Team `+0x124`, u32 | PROVED OFFLINE | Payroll, recomputed by `C3F00` across active contracts plus IR charges. |
| Team `+0x19C..0x1A8`, seven u16 entries | PROVED OFFLINE | Annual dead-money ledger; `13ED70` shifts it at rollover. |
| `E5FE0` / `E6000` | PROVED OFFLINE | Convert between stored total units and game thousands. |
| `E6380` / `E6020` | PROVED OFFLINE | Current base salary / annual amortized bonus; both enter cap payroll. |
| `13ECA0` / `13ED00` / `13ED30` | PROVED OFFLINE | Available cap / remaining bonus liability / penalty ledger writer. |
| `2BF950` | PROVED OFFLINE | Combined upper roster-count and current-payroll gate. |
| `4FE7A0`, float32 | PROVED OFFLINE | Future-cap and rollover growth multiplier. |
| Save front office `+0x15D0` | PROVED OFFLINE | Serialized cap, absolute `0x9ACCC` in the existing franchise layout. Existing EXTRA/HMAC-SHA1 save signing remains in use. |

DESIGN: generated player value uses the mean of five cited leading APYs per engine position, multiplied by `clamp((OVR - .45) / .55, 0, 1)^3`, current modeled cap growth and an experience decline. Native years-pro proxies age (INFERRED); decline thresholds and the eight-percent annual reduction, bounded at one quarter, are design assumptions. CBA minimum targets bound generated demand. Values saturate at 60,000 game thousands because callers narrow to AX. All source names, URLs, APYs and thresholds remain in [the phase 1 source data](../data/nfl2k5_franchise_economy.json).

DESIGN: trade surplus adds half of modeled annual value minus current cap cost for up to four remaining years. Both sides receive that treatment. Pick value reproduces the first 224 entries of the [OTC Fitzgerald-Spielberger chart](https://overthecap.com/draft-trade-value-chart), scaled by two; future picks use a modeled middle-round slot and three-quarter discount. Native fixed rounds do not gain compensatory ownership. These conversions model game decisions, not a published NFL acceptance formula.

PROVED OFFLINE: `2BAE90` checks trade legality, cap/roster constraints and values. `2BB760` computes the score; `2BC380(interactive=1)` takes the native CPU acceptance path. Noninteractive acceptance bypasses the score and is not used as decision proof. [Twelve native trade cases](proof/trade_cases.json) were rerun against the final patch: first overall for a seventh-round first slot accepts, the reverse rejects, a current first for an identical first rejects at the retained CPU threshold, and the documented Giants package for pick 25 accepts while a hypothetical reduced package rejects. Player-cost/position/experience cases are explicitly labeled test scenarios. The [Giants' published package](https://www.giants.com/news/jaxson-dart-trade-details-nfl-draft-room-joe-schoen-brian-daboll-abdul-carter-ole-miss) is picks 34 and 99 plus a future third; the mapping to fixed native slots is INFERRED. No empirical validation across NFL trades is claimed.

## PROVED OFFLINE: roster/cap failures, root causes and fixes

PROVED OFFLINE: phase 1's synthetic rollover exceeded the unchanged 54-player combined gate because native `246F90` returned IR players to already full rosters. A regression fixture using real retail player records demonstrates 53 active plus three returning IR players becoming 56, then the corrected native transaction path reaching 54 with the gate passing. The fixture is a test of the mechanism, not NFL injury data.

DESIGN: replace the CPU cap-cut routine at `2BFBE0` and call it at the rollover's salary-recompute site `247BC6`. The bounded reconciliation recomputes payroll, releases the lowest native-OVR eligible player, preserves two quarterbacks and one of every other occupied position, and stops at 42 players. Releases go through the native penalty and free-agent transaction paths. The salary/roster gate `2BF950` remains untouched; no pass result is forced.

PROVED OFFLINE: the first real-data run passed all teams at start and rollover, then failed after free agency: Cleveland had 56 players; the Rams, Ravens and Titans exceeded the cap. [Preserved failed run](proof/real_rollover_before_signing_fix.json). Native direct CPU filling at `322BB0` received an unlimited CPU budget and could add several players after one outer roster check. Native timed acceptance at `323B30` had no commit-time cap/roster check and wrote value/term while retaining the old deal's curve/bonus.

DESIGN: a guarded six-byte trampoline at `322BB0` checks each fill for fewer than 54 players and caps the budget at actual room less a small rounding reserve. Another at `323BB3`, after the native consent test, calculates the offer's actual first-year base plus bonus, rejects insufficient room/full rosters, and writes the new curve/bonus before resuming the original transaction body. Native player consent, ownership, FA removal, transaction records and offer cleanup remain in the original code. A normal-consent regression proves rejection before mutation, successful new-term accounting, and refusal of a 55th fill.

PROVED OFFLINE: a second full run exposed automatic CPU renewals at `322EB0`, which generate deals directly without going through timed offers. The Rams and Ravens remained over cap after reaching the reconciliation floor of 42 players. [Preserved run before renewal fix](proof/real_rollover_before_renewal_fix.json). This was not fixed by weakening the roster floor or forcing the cap gate.

DESIGN: the guarded seven-byte renewal entry now checks the generated balanced deal against available room after excluding the player's existing charge. The old record and payroll are restored before the decision. An unaffordable renewal returns before contract generation or transaction logging; an affordable renewal resumes the native body. Its regression checks refusal without player/payroll mutation and successful native renewal when room exists.

PROVED OFFLINE: generated code fits within the guarded retail windows: valuation/helpers 1,020/1,082 bytes, contracts/helpers 204/215, rookies/market constants 278/280, picks 344/403, money/fill helper 172/198, reconciliation/helpers 345/370. No allocated cave or new save storage is needed. [Runtime source](../tools/franchise_economy/runtime.c), [guards and patch owner](../mod_editor/core/nfl2k5_franchise_economy.py).

## PROVED OFFLINE: native proof and OTC comparison

PROVED OFFLINE: the final real-source run completed in 884.790 seconds: 268 native fixture simulations, 268 stat commits, one rollover and year 1, stage 4 after re-signing/free agency. All 32 teams pass both cap and unchanged combined gate at all three checkpoints. No informational notices, unexpected decision dialogs or instruction-budget stops occurred. Call counts are visits, not accepted-transaction counts. [Final native artifact](proof/real_rollover.json).

| Checkpoint | Evidence | Cap, real $M | Cap pass | Combined gate | Active players |
|---|---|---:|---:|---:|---|
| Start | PROVED OFFLINE | 301.200 | 32/32 | 32/32 | 53 |
| Immediately after rollover | PROVED OFFLINE | 324.932 | 32/32 | 32/32 | 54 |
| After free agency | PROVED OFFLINE | 324.932 | 32/32 | 32/32 | 34 through 54 |

PROVED OFFLINE: patched XBE SHA-256 `388486abb397d58856157ccb2c61e5fefc06b4a0d3f4f994bf7eede1865025fc`; composed roster SHA-256 `a4036686e6d7400d5def1e9aab15e73b841b67b2bececc7a90c41cde53ac1d34`. The text dump and lab preparation use this same composed roster. `native_financial_gates_proved` is true; `release_proof` remains false for the representation reasons above.

PROVED OFFLINE: the native runner uses r1's `tests/nfl2k5_supersim_draft_fixture.Machine`, frozen u7 names, unchanged r1 v2.4 ratings and the real fc fragment. It advances actual native MyNFL transitions. Progress rendering and informational dialogs are the only substituted leaves. It fails on an unexpected decision dialog. At postseason exit it registers one owner through the native setter because the zero-owner branch ends MyNFL. It never substitutes an acceptance or financial-gate result.

PROVED OFFLINE: this isolated economy probe retains the retail season structure. It does not prove the actual 2026 NFL schedule, final composed disc, Xbox rendering or save-device I/O. Main's lab recipe includes the separate modern season/naming options and needs its own final-payload witness.

PROVED OFFLINE: [all-team cap table](proof/TEAM_CAP_TABLE.md) shows start and immediate rollover payroll, space and effective dead money against the [OTC 2026 team table](https://overthecap.com/salary-cap-space), observed September 25. [The CSV](proof/team_cap_comparison.csv) retains exact dollars, ledger dead money, roster counts and all three checkpoints, including subsequent free agency. [Captured OTC values](data/otc_team_caps_2026.json) cover every club.

DESIGN: the comparison is intentionally not a reconciliation claim. The frozen 53-player club roster differs from OTC's accounting roster. The experiment has a uniform $301.2M cap, no imported historical dead money, no team carryover or other cap adjustments, quantized fits and 259 modeled schedules. Native legacy dead money is zero while OTC often reports substantial dead money. The simulated next-year roster is compared with 2026 only as a reference, not a forecast. Passing the native upper-count/cap gate does not prove a complete 53-player NFL roster or modern CBA compliance.

## PROVED OFFLINE: build plumbing, validation and transport

PROVED OFFLINE: the phase 1 changes in `mod_editor/core/nfl2k5_throw_tuning.py` are required build plumbing. Despite its historical name, that file owns the shared XBE/disc copy pipeline. The changes import the economy writer, accept and forward the flag, include it in the requested-work guard, apply the guarded patch, and report its status/receipt in both copy paths. They do not change throwing physics or pass tuning. No unrelated portion needs reverting; phase 2 leaves that file unchanged.

PROVED OFFLINE: `franchise_economy` remains false in all presets. The GUI and registry describe real-dollar display with fitted contracts and keep runtime status `not-tested`. The provider closure and GUI hashes are repinned. The two broader registry-dependent tests blocked by the pre-existing missing `U3_TEAM_IDENTITY_2026-09-23.md` are outside fc; no dummy file or validation relaxation was added.

PROVED OFFLINE: 60 tests passed: 23 economy/import/native tests and 37 Build, offscreen GUI and provider tests. Generated-code reproduction, lab shell/Python syntax, zero-log lab composition, matching text/season hashes, canonical registry/economy evidence paths and `git diff --check` passed. [Validation receipt](proof/validation.json).

DESIGN: The private git repository is `.scratch/fc.git`, based on `9ce0787e5605f3e2f8caaa921c970ef42a69595a`; the incremental bundle is `.scratch/fc-phase2.bundle`. Main can inspect `git bundle list-heads` and fetch its advertised `job/b76-fc` head. Shared git metadata is read-only here. Only explicit task paths are committed, with the required Astra co-author trailer; no push or tags.

## DESIGN: reproduction and Main's lab

DESIGN: reproduce the import, guarded code and native evidence with these commands from the worktree. The full season takes roughly fifteen minutes on this host.

```sh
python3 tools/franchise_economy/import_contracts.py \
  --base /media/noah/Storage/.b76-research/main/freeze/league_roster_edits_u7_names.json \
  --players /media/noah/Storage/.b76-research/r1/data/nflverse/players.csv.gz \
  --contracts /media/noah/Storage/.b76-research/fc/data/historical_contracts.json --out fc/data
python3 tools/franchise_economy/assemble.py --check
python3 -m unittest tests.mod_editor.test_franchise_economy
python3 tools/franchise_economy/probe.py \
  --base /media/noah/Storage/.b76-research/main/freeze/league_roster_edits_u7_names.json \
  --ratings /media/noah/Storage/.b76-research/r1/deliver/v2.4/r1_ratings_v2.4_fragment.json \
  --fragment fc/data/fc_contract_fragment.json --out fc/proof/real_rollover.json
python3 tools/franchise_economy/money_probe.py \
  --base /media/noah/Storage/.b76-research/main/freeze/league_roster_edits_u7_names.json \
  --ratings /media/noah/Storage/.b76-research/r1/deliver/v2.4/r1_ratings_v2.4_fragment.json \
  --fragment fc/data/fc_contract_fragment.json --out fc/proof/money_strings.json
python3 tools/franchise_economy/summarize.py
```

DESIGN: Main runs `bash fc/lab/fc_lab.sh` only as an experiment. It checks the frozen-base binding and zero-log composition, writes an offline text baseline, builds through the existing builder on Storage, verifies final economy inspection, takes the shared xemu lock and uses an isolated HDD/config. The unwitnessed menu route attempts finances and trade, records explicit misses and submits no trade. Main must inspect contract/negotiation/card/list screens and clipping as well; the scripted route does not prove those live screens. Lab output defaults to `/media/noah/Storage/.b76-research/fc/lab2`. No generated disc or source parquet is copied to the NVMe.

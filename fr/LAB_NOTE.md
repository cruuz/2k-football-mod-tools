DESIGN: Candidate G MyNFL lab note for main, 2026-09-29.

PROVED OFFLINE: Frozen edits SHA-256 `983eeeb076b7b6b30587def0fd6c6f31c3daea4d7c4efbffd5828646c0d9dfde`. Offline roster body SHA-256 `699ec8974a2649ba98d9a9257fbccb87e36f99ed8cae0ce22138992c06c84037`. The data/native probes do not render these screens.

DESIGN: Build with the private FR commits, candidate F settings and the G roster path. Retain calendar_engine, season_2026, team_column and franchise_economy. Start a brand-new ordinary MyNFL franchise with cap enabled; old saves retain their own data. Record disc hash, build recipe, roster hash, team, date, franchise year and new-save status with every capture set.

| Evidence | Screen | Required comparison |
| --- | --- | --- |
| DESIGN | Front Office salary/cap summary, DEN/BUF/SF | Global cap $301.20M; compare payroll to `fr/proof/team_totals.json`. Distinguish roster payroll from real adjusted NFL cap space. |
| DESIGN | Contracts, Josh Allen BUF | G five-field opening cap $44.248M, five years remaining. Capture every displayed year and use the exact ledger, not original-deal cash, as the model comparison. |
| DESIGN | Contracts, Garett Bolles DEN and Andre Jones MIA | Bolles G opening cap $13.216M; Andre G $0.952M and two remaining years. Record displayed precision. |
| DESIGN | Contract/offer boundary, Wydett Williams ARI | G one-year fallback $0.920M. Runtime rookie offer floor is $0.888M; these use different charge lattices. Test acceptance on a disposable save and record actual terms. |
| DESIGN | Player cards, Josh Allen and Patrick Mahomes | Clean 2026 current rows; Allen 2025 passing 3,668 and career 30,072, TEAM BUF; Mahomes 2025 3,587 and career 35,939, TEAM KC. Capture all older rows and Total. |
| DESIGN | Cards, Barkley PHI and Henry BAL | Barkley 2025 rushing 1,140 and career 8,356; NYG through 2023, PHI from 2024. Henry TEN through 2023, BAL from 2024. |
| DESIGN | Card, Aaron Rodgers PIT | 2025 passing 3,322; career 66,267. GB through 2022, NYJ 2023-2024, PIT 2025. Old seasons outside the 15-row window remain separate in the initial data; do not assume a pre row is already manufactured. |
| DESIGN | Cards, Purdy SF and Jefferson MIN index 841 | Purdy 2025 passing 2,167, career 11,685. Jefferson 2025 receiving 1,048, career 8,480. Distinguish the Cleveland player with the same name. |
| DESIGN | Kicker card, Matt Prater | Check made/attempted distance buckets, total attempts and percentage. Blocked attempts count in their distance bucket. Use the player ledger in `native_stats.json` or embedded G seasons for exact expectations. |
| DESIGN | Defender card | Compare the declared combined-tackle value with source categories and check how native gameplay credits assists. The import policy is explicit; gameplay equivalence remains unproved. |
| DESIGN | Bios, Bam Knight and Elijah Wilkinson ARI; Kyle Hinton ATL; Garett Bolles DEN | Knight North Carolina St, Wilkinson UMass Amherst, Hinton Washburn. Capture DOB, HT, WT, COLLEGE, YRS PRO and portrait. OL has no native stats table. |
| DESIGN | Bios, Godrick, Okoye, Stiggers, Mailata | Confirm older-source college fallback labels from `fr/proof/colleges.json`, including explicit No College where sourced. |
| DESIGN | Free-agent list, all position filters and sorting | Compare 236 identities to `fr/proof/free_agents.json`; Kenny Holmes, Kurt Kittner and Antowain Smith must not appear. Also check the five removed historical FA aliases. Reserve/DEV/EXE names are not falsely unsigned. |
| DESIGN | CPU refill on disposable franchise | Create roster/cap room, advance through CPU transactions, inspect signings and repeat after save/reload. No retail identities should re-enter the FA/signing path. Offline proof covers initialization and 17 native fill cases. |
| DESIGN | Special-teams depth charts, ARI/DET/HOU/MIN | Reconfirm F's proved KR/PR selections and LS. Their input and all six role bytes per team are unchanged; capture game rendering on G. |
| DESIGN | Trade and rollover, one season then at least three | Capture TEAM before/after trade, season end, history folding, career totals, contract progression, cap and save/reload. TEAM has one franchise per season. |
| DESIGN | J.J. McCarthy membership review | G deliberately retains F's MIN membership, while current annual nflverse says NYG. Resolve this separately without silently changing proved depth charts. |

DESIGN: Report any wrong value with the exact index/GSIS ID, screenshot, build hash and save age. Keep PROVED OFFLINE, DESIGN, INFERRED and actual in-game observations distinct.

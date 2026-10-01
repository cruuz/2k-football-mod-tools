"""PROVED OFFLINE: render the FR handoff from pinned measurements."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'fr/proof'
def read(n):return json.loads((P/n).read_text())
p=read('preservation.json');audit=read('before_after.json');native=read('native_stats.json');cpu=read('cpu_free_agents.json')
contracts=read('changed_contracts.json');teams=read('team_totals.json');colleges=read('colleges.json');minimums=read('minimums.json')
fields={r['field']:r for r in audit['fields']}

def pair(name):
    r=fields[name]
    return f"{r['before_mismatch']}/{r['before_checked']} → {r['after_mismatch']}/{r['after_checked']}"

lines=[
'PROVED OFFLINE: FR candidate G franchise handoff, 2026-09-29.',
'',
'PROVED OFFLINE: The six requested implementation passes are committed in order in a private git. Candidate G replaces 1,932 identity-owned histories, sources season TEAM entries, seeds 236 current unsigned identities, corrects colleges, refreshes 24 observed contract schedules, and ceilings all current minimum fallbacks. This report describes decoded roster bytes and bounded native instruction tests. No disc build or xemu run was performed.',
'',
'DESIGN: This is a new 2026 preseason franchise with completed regular seasons through 2025. It retains F\'s 53-man rosters and all dc depth-chart selections. It is not a September live-stat save, a full transaction update, or an exact cash/guarantees contract model.',
'',
'PROVED OFFLINE: Frozen deliverable: `/media/noah/Storage/.b76-research/main/freeze/candG/league_roster_edits_candG_fr.json`.',
f"PROVED OFFLINE: G file SHA-256 `{p['g_sha256']}`. Decoded body SHA-256 `{p['body_sha256']}`.",
f"PROVED OFFLINE: F input SHA-256 `{p['f_sha256']}`. Base commit `6bd9b3d66d239a267f8d4f66e083b8a6eb320671`.",
'',
'PROVED OFFLINE: The original six commits are `0f5b1624` stats, `f55c598b` TEAM, `ffc467fe` free agents, `d47a6b97` colleges, `66fe9f21` contracts, and `c807a786` minimums. The final handoff commit adds validation, complete attempted-FG buckets, the documented tackle policy, and a tested build-history stage. All use the requested Co-Authored-By trailer. The private git is `/media/noah/Storage/.b76-research/fr/private.git`; the verified transfer bundle and its receipt are `/media/noah/Storage/.b76-research/fr/fr.bundle` and `bundle_receipt.json`. No push or tags.',
'',
'PROVED OFFLINE: Sources are nflverse contributors, CC-BY-4.0. All 54 cached data assets were rehashed before generation. [Source manifest](fr/proof/source_manifest.json) retains each source URL, release date, retrieval date and SHA-256, plus derived identity/audit/freeze input pins. The current contract Parquet is `8295dfb366de9e0ea9a98bdf45f034d75b66bda74c09c723b5bceab2688b4316`, updated 2026-09-29 13:56:25 UTC. The old CSV contract asset was not used. No Spotrac source was accessed.',
'',
'DESIGN: Existing F rookie model targets remain explicitly modeled when current annual schedules are unavailable. Their prior model provenance is retained; they are not newly observed nflverse contracts. No new external contract data was imported. Owen Pappoe has no active current contract candidate, so his prior observed deal is replaced with a labeled one-year minimum model.',
'',
'PROVED OFFLINE: [Preservation proof](fr/proof/preservation.json) verifies all 6,162 original edit objects as an unchanged prefix, every original top-level value, 224,143 non-target named field values, all 52 complete team records, all 32 special-team entries with 192 role bytes, and all 615 unrelated history streams. Unexpected named-field differences: zero. [Intended field differences](fr/proof/changed_fields.csv) records every changed scalar. Team membership, ratings, equipment and the ARI/DET/HOU/MIN proved KR/PR selections are preserved for F team players.',
'',
'PROVED OFFLINE: `mod_build._apply_roster_history` applies identities before optional counters, then TEAM. Embedded G history owns both counters and TEAM; a conflicting career CSV is refused, the build epoch must match 2026, and the retail TEAM fallback is suppressed. Prospect-name and tag writers retain their position before roster edits. The build-stage tests execute this ordering without creating a disc.',
'',
'PROVED OFFLINE: Replacement histories are pinned by pool/index, new first/last name, DOB and GSIS ID. Entire donor streams, including deleted, postseason, unknown and orphan current/future words, are removed only for the 1,932 selected identities. Unrelated streams remain exact. Missing modern source seasons are left unverified and do not retain donor values. Zero counters are sparse; every stored season has positive sourced games.',
'',
f"PROVED OFFLINE: The final pool uses {p['pool']['used_after']:,}/50,000 dwords, leaving {p['pool']['free_after']:,}. It contains 6,203 sourced player-seasons, including 6,011 for the 1,696 team players. Pool ownership, nonzero slack, capacity, terminators and decode-back verification are checked transactionally. Current seasons are clean for all 1,932 identities after native MyNFL initialization.",
'',
'DESIGN: Seasons older than the native 15-row window remain separate for lossless career addition. They are not compressed into an overflowing 16-bit career cell. The initial import does not manufacture a folded pre row; native folding/rollover behavior remains a lab check. Aaron Rodgers\' passing career is 66,267, not a truncated season cell.',
'',
'PROVED OFFLINE: FA\'s audit was rerun against G\'s decoded bytes using [the explicit adapter](fr/rerun_fa.py). It preserves the source joins and original 26-counter comparisons, reads actual field-87 words instead of predicting retail additions, and compares contract integrity against the new fragment. [Before/after per field](fr/proof/before_after.csv) includes every original comparison, its denominator, and five supplemental source-defined counters. Full rerun outputs are in `/media/noah/Storage/.b76-research/fr/audit_g/`.',
'',
'PROVED OFFLINE: TEAM results change from 1,530 wrong / 20 absent / 2,920 missing stats-backed rows to 0 / 0 / 0. G has 5,002 matching displayed team-player rows. The adapter normalizes all existing franchise aliases, including HST/BLT/SL; without that correction, 21 correct G rows are falsely flagged by FA\'s shorter alias map. The 254 roster-only seasons without sourced stats remain unscored.',
'',
'DESIGN: One TEAM is selected from the latest week in the annual GSIS roster. A tied week uses the season stats recent_team only when it is among those annual candidates. Keenum 2014 resolves to HOU by week 17; Quinnen Williams 2019 resolves to NYJ by corroboration. It does not represent every club in a multi-team season. Historic franchise labels use the game\'s current abbreviation.',
'',
'PROVED OFFLINE: Counter mismatches below compare source-defined regular-season values. Original FA denominators are preserved. Each cell is before mismatch/checked → after mismatch/checked.',
'',
'| Evidence | Counter | 2025 | Career |',
'| --- | --- | --- | --- |']
for name in sorted(k[5:] for k in fields if k.startswith('last_')):
    evidence='DESIGN' if name=='defensive_tackles' else 'PROVED OFFLINE'
    lines.append(f'| {evidence} | {name} | {pair("last_"+name)} | {pair("career_"+name)} |')
lines += [
'',
'PROVED OFFLINE: Field-goal attempt buckets use all made, missed and blocked distance lists, validated against component counts and total attempts. All 4,965 source kick distances balance. This follows [nflfastR calculate_stats](https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R); the exact downloaded source hash and date are pinned in `fr/stat_semantics_source.json`.',
'',
'DESIGN: The imported tackle value is combined participation: solo tackles + primary tackles with assistance + tackle assists, disjoint source stat IDs 79/80/82. This policy is explicit; equivalence to every native gameplay assist-credit convention is not proved. FA originally left this counter unscored. Other native statistics outside the 31 mapped counters are not claimed accurate, and stats-row games are not a credited-season or complete participation measure.',
'',
'PROVED OFFLINE: [Native getter evidence](fr/proof/native_stats.json) executes 59,892 career-counter checks, 6,203 games/TEAM row checks, 1,932 college-label checks, and all 32 payroll/cap checks after bounded MyNFL initialization. There are no substituted routines. These tests prove the data and native getters, not rendered screens, formatting precision or multi-season persistence.',
'',
'PROVED OFFLINE: The unsigned pool contains exactly 236 replacements, all from dated nflverse CUT entries and disjoint from the 1,696 team identities. Five additional raw FA aliases, Larry Centers, Charlie Clemons, Jason Gildon, Jeremiah Trotter and Shannon Sharpe, are removed from free-agent membership while their historical records survive. [FA ledger](fr/proof/free_agents.json) pins each replacement and any older annual bio source used to fill missing 2026 data.',
'',
'DESIGN: The 236-slot selection prefers the donor position, then experience and stable GSIS ID. Ratings and appearance remain gameplay templates, not nflverse ratings or likeness claims. Unsigned contract fields are zero; native signing creates the new deal. The dated RES/DEV/EXE list is retained in `/media/noah/Storage/.b76-research/fr/reserve_snapshot.json`; these players are excluded from unsigned membership and no F active-roster ownership is changed.',
'',
'PROVED OFFLINE: [CPU evidence](fr/proof/cpu_free_agents.json) verifies the entire 236-pointer pool survives native initialization and successfully executes one CPU signing for each of 17 position codes. All 17 signed identities are modern; no financial, selection, membership or transaction routine was substituted. The test grants financial room to isolate eligibility. This is bounded start/refill proof, not an indefinite rollover claim.',
'',
'PROVED OFFLINE: Colleges change from 160/1,692 source-school disagreements to 0/1,692. Four missing current team-player colleges resolve from older nflverse annual rows. Including free agents, 398 player colleges change. The 67 new source labels reclaim unreferenced table slots; UTF-16 suffix sharing keeps the same 266-entry table and original string span. Every referenced unrelated school remains unchanged. [College ledger](fr/proof/colleges.json) records sources and alias slots.',
'',
'PROVED OFFLINE: Contracts resolve as 1,439 observed schedules and 257 models. All 24 changed observed schedules are reviewed in [the contract comparison](fr/proof/changed_contracts.json). Andre Jones now has two represented years. All observed opening-year errors are within $20,000; the maximum is $20,000. Exact opening charges, future curves and cash fields still have expected five-field model differences in the per-field audit.',
'',
'| Evidence | Changed schedule | Old source 2026 | New source 2026 | G represented 2026 | Remaining years old → G |',
'| --- | --- | ---: | ---: | ---: | --- |']
for r in contracts:
    lines.append(f"| PROVED OFFLINE | {r['name']} | ${r['old_source_cap'][0]:,} | ${r['fit']['source_cap_dollars'][0]:,} | ${r['fit']['represented_cap_dollars'][0]:,} | {r['old_fields']['contract_remaining']} → {r['fit']['fields']['contract_remaining']} |")
lines += ['',
'PROVED OFFLINE: The original 50 minimum fallback cases are individually tracked in the preservation receipt. Three now have observed source schedules; 47 remain minimum models. Adding Pappoe gives 48 current minimum fallbacks, all at or above their own floor. A prorated observed cap charge is not reclassified as an illegal full-season fallback.',
'',
'DESIGN: Years pro remains the credited-seasons proxy. `fit_minimum` uses the smallest representable one-year charge: $920k, $1.040m, $1.080m, $1.160m, $1.240m or $1.320m for the six bands. The one-year charge step is $40,000; the runtime offer floor has a finer $4,000 step. The tests verify that the next lower stored value fails the floor under every supported curve and bonus choice.',
'',
'PROVED OFFLINE: All 32 decoded 53-player totals below agree with native salary walkers and fit the unadjusted $301.2M cap. [Team totals](fr/proof/team_totals.json) separate sourced and modeled schedules. These are opening roster payrolls, not real adjusted cap-space accounting with carryover, dead money and accounting-only years.',
'',
'| Evidence | Team | Observed / 53 | G payroll | Room against $301.2M |',
'| --- | --- | ---: | ---: | ---: |']
for r in teams:lines.append(f"| PROVED OFFLINE | {r['team']} | {r['observed']}/53 | ${r['payroll']:,} | ${r['room']:,} |")
lines += ['',
'PROVED OFFLINE: DOB, height, weight and years pro remain at zero team-player source mismatches. The pre-existing J.J. McCarthy discrepancy remains: F/G retains MIN while the current annual source says NYG. This task preserves F\'s active memberships and proved depth charts; that dated roster-policy decision remains for main.',
'',
'PROVED OFFLINE: Validation consists of 38 focused unit tests, the native getter/payroll/college probe, and the 17-position CPU signing probe. `fr/proof/validation.json` records commands and measured process peaks. The largest peak is 545,276 KiB; concurrently run audit/probes together remain below 1.5 GB. Work stayed on cores 24-31. Candidate F\'s completion marker was not yet present, so no broad suite, disc build or emulator run was started.',
'',
'PROVED OFFLINE: Reproduce from this worktree with `taskset -c 24-31 env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 fr/generate.py`, then copy its JSON from the FR scratch directory to the specified candG path. Run `fr/rerun_fa.py`, `fr/probe_stats.py`, `fr/probe_free_agents.py`, and `fr/verify.py` with the same prefix. Data remain in FA\'s pinned cache, including its local pyarrow. No source cache, F freeze or disc path is written.',
'',
'DESIGN: Main should merge the private bundle on the F base and select the G roster file with calendar_engine, season_2026, team_column and franchise_economy enabled. Embedded history makes a separate career CSV unnecessary. Follow [the G MyNFL lab note](fr/LAB_NOTE.md) using a brand-new save. Screens and rollover are still required before describing the complete franchise as proved in game.',
'',
'INFERRED: The requested data and native-read paths are substantially corrected. Full visual accuracy remains bounded by the 31-counter mapping, the declared tackle policy, the preserved McCarthy membership discrepancy, sparse source coverage, the five-field contract model and pending lab captures.',
'',
'PROVED OFFLINE: Candidate G is frozen at the requested path with a recorded SHA-256.',
'PROVED OFFLINE: Six implementation commits follow the requested order, followed by the validation handoff.',
'PROVED OFFLINE: All 6,162 original F edit objects and original metadata are preserved.',
'PROVED OFFLINE: All 52 team records and dc\'s 192 special-team role bytes are unchanged.',
'PROVED OFFLINE: All 615 unrelated history streams are preserved exactly.',
'PROVED OFFLINE: The 1,932 replacement histories use 33,295 of 50,000 pool words.',
'PROVED OFFLINE: All original 26-counter 2025 and career audit mismatches fall to zero.',
'DESIGN: Four attempted-FG counters and combined tackles add explicit source-defined coverage.',
'PROVED OFFLINE: Wrong TEAM, absent TEAM and missing stats-backed display rows all fall to zero.',
'PROVED OFFLINE: The 236 modern unsigned identities survive initialization; 17 CPU signings use only modern identities.',
'PROVED OFFLINE: The 160 team-player college disagreements fall to zero.',
'PROVED OFFLINE: All 24 changed observed contracts are refreshed and all 32 opening payrolls fit $301.2M.',
'PROVED OFFLINE: All 48 current minimum fallback charges meet the smallest representable floor.',
'PROVED OFFLINE: 38 focused tests and the native probes pass without a disc build or xemu.',
'DESIGN: Main still needs the G screen and rollover captures; model and source limitations remain explicit.',
'ASTRA_DONE']
text='\n'.join(lines)+'\n';assert '\u2014' not in text
(ROOT/'FR_REPORT.md').write_text(text)

lab=f'''DESIGN: Candidate G MyNFL lab note for main, 2026-09-29.

PROVED OFFLINE: Frozen edits SHA-256 `{p['g_sha256']}`. Offline roster body SHA-256 `{p['body_sha256']}`. The data/native probes do not render these screens.

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
| DESIGN | Special-teams depth charts, ARI/DET/HOU/MIN | Reconfirm F\'s proved KR/PR selections and LS. Their input and all six role bytes per team are unchanged; capture game rendering on G. |
| DESIGN | Trade and rollover, one season then at least three | Capture TEAM before/after trade, season end, history folding, career totals, contract progression, cap and save/reload. TEAM has one franchise per season. |
| DESIGN | J.J. McCarthy membership review | G deliberately retains F\'s MIN membership, while current annual nflverse says NYG. Resolve this separately without silently changing proved depth charts. |

DESIGN: Report any wrong value with the exact index/GSIS ID, screenshot, build hash and save age. Keep PROVED OFFLINE, DESIGN, INFERRED and actual in-game observations distinct.
'''
assert '\u2014' not in lab
(ROOT/'fr/LAB_NOTE.md').write_text(lab)
print('wrote FR_REPORT.md and fr/LAB_NOTE.md')

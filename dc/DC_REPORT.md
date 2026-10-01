# PROVED OFFLINE: dc special-teams depth import, 2026-09-28

PROVED OFFLINE: candidate C's unchanged retail special-index bytes reproduce the wrong modern returners. Native loading and lineup selection use those indices immediately; the existing returner-fix option does not repair stale roster assignments. This delivery changes KR1 on 31 teams, KR2 on 28, PR on 29, LS on 25 and holder on 15. K and P already select the snapshot players. [All 32 teams, stored bytes and actual native picks](proof/SPECIAL_DEPTH.md).

PROVED OFFLINE: all supplied primary KR, PR, K, P and H assignments with available roster identities are imported in snapshot order. Missing entries advance to the next available entry. Four role lists are exhausted: CLE and DAL KR2, DEN and NO LS. These have explicit DESIGN fallbacks, not claims of complete NFL accuracy. The report retains every missing entry, including unused backups. [Matching and exceptions](proof/MISSING_PLAYERS.md).

INFERRED: the stale-index mechanism explains Noah's reported strange returners. No captured play from his running game was supplied, so this is a reproduction from C's build inputs, not identification of a particular recorded kickoff.

## PROVED OFFLINE: selection path and why sorting alone is insufficient

| Native path | Evidence | Behavior |
|---|---|---|
| Roster load `0xC0500`, team relocation `0x2418C0` | PROVED OFFLINE | Converts relative pointers. Native execution calls neither `0x2BDCF0` nor `0x243790` during this load path. It leaves the six special-index bytes intact. This does not assert that every mode-entry routine is free of additional depth work. |
| Team indices | PROVED OFFLINE | `+0x194` holder, `+0x195` KR1, `+0x196` KR2, `+0x197` legacy K, `+0x198` legacy LS, `+0x199` PR. These are team slots, not primary-player IDs or depth ranks. |
| Chart getter `0x242AE0` / `0x242A60` | PROVED OFFLINE | KR pseudo-position 254 reads KR1/KR2; PR 253 reads PR. Positional rows read the rank/side bitfields at player `+0x28`. |
| Native list builder `0xE80D0` / `0xE7C50` | PROVED OFFLINE | Builds dense position lists from rank/side and eligibility. Seeds KR with KR1, KR2, distinct PR; seeds PR with PR, distinct KR2, distinct KR1. Seeds holder from `+0x194`. It does not validate an explicit returner's position against the ratings-selector mask. |
| Personnel resolver `0xE7530`, picker `0xE8790`, whole lineup `0xE89F0` | PROVED OFFLINE | PLAY kind 4 even ordinals select KR, odd ordinals PR. Normal Kick Return uses codes 4 and 68, so KR1 and KR2; Punt Return uses 36, so PR. Holder is kind 3, K kind 2, P kind 1. Punt/FG LS is C kind 6 ordinal 1, code 38. The picker skips an already-assigned identity and has short-list/eligibility fallbacks. |
| Franchise auto-depth `0x2BDCF0` | PROVED OFFLINE | Runs before and after week advancement and on the documented draft-stage path. Same-position overall sorting can reorder team pointers and invalidate special indices. C has the returner-fix and depth-lock options enabled through its experimental preset. |
| Existing fixed ratings selector `0x2BDE70..0x2BDFD0` | PROVED OFFLINE | Scans the full roster, ranking native category-10 returner scores. First excludes starters; a second pass fills otherwise-empty roles from eligible starters. KR allows WR/CB/FS/SS/HB/FB; PR allows WR/CB/FS/SS/HB. Strict score comparisons retain earlier roster candidates on ties. It is a fallback/auto-depth policy, not current NFL depth data. |
| Existing lock-aware compactor `0x243790` | PROVED OFFLINE | Resolves KR1/KR2/PR player lock bits to their current roster indices after reordering. Rank locks retain the imported K/P/LS rows. C's single-punter holder on every team is unchanged by same-position pointer sorting. |

PROVED OFFLINE: C's native unsorted lineup fields Casey Kreiter at ARI KR1, Skyler Gill-Howard at DET KR1, Hogan Hatten at DET KR2, Andrew DePaola at MIN KR1 and Tanner Koziol at JAX KR1. These are direct examples of stale indices surviving the player-name replacement. The native ratings selector excludes their positions, but that selector is not invoked by the measured roster-load path. [Raw native before/after/auto-sort evidence](proof/native.json).

PROVED OFFLINE: the retail PR score-to-index conversion bug and KR2 score-tracking bug are already fixed by C's returner-fix option. This job does not alter those executable patches. The earlier [depth-lock report](../ASTRA_DEPTH_LOCKS_REPORT.md) and [follow-up](../ASTRA_DEPTH_LOCKS_FOLLOWUP.md) supply the detailed call sites and layout ownership; current native execution confirms this job's identities.

PROVED OFFLINE: after the first revised auto-depth pass, the legacy LS index byte is invalidated to 255 on 24 teams. Their actual snapper selections remain correct because these formations use the locked second-center list. Persistence here means stable native selections, not preservation of every legacy index byte. Holder, KR1, KR2, K and PR index bytes remain valid on all 32 teams in this probe.

## DESIGN: import and roster-edits representation

PROVED OFFLINE: the latest snapshot per team is `2026-09-28T06:01:42Z`, with 2,296 rows and 330 special-teams entries. Matching uses the existing fc identity ledger keyed by primary-pool/index and checked against the current name, then GSIS ID within the active team. Normalized-name fallback is implemented and tested. Actual results: 298 GSIS matches, zero name fallbacks, 32 missing team entries. The 2025 snapshot is not used to infer current assignments.

PROVED OFFLINE: those 32 missing entries have neither a normalized-name match anywhere in C nor a name-verified GSIS match in its identity ledger. They are not present on another current roster team or in its reserve records under either matching method. All 329 provider module hashes also match. [Additional checks](proof/additional_checks.json).

DESIGN: source attribution is nflverse contributors, `nflverse-data` depth_charts release, CC-BY-4.0. The supplied 2026 CSV and identity-ledger hashes are retained in [import.json](proof/import.json). Team aliases are ARZ to ARI, SD to LAC, OAK to LV and STL to LA. Missing players are not signed, created, renamed or moved in this job.

DESIGN: [special_depth_fragment.json](special_depth_fragment.json) adds only player `depth_rank` and `unknown_52` changes plus a new optional `special_teams` list in the existing roster-edits schema. Each role names a pool/index and current first/last name, rather than carrying a fragile team-slot number. Replay resolves identities after name and membership replay. It validates the whole specialist list before writing and refuses unknown roles, mismatched teams, stale names, absent/nonmember players and duplicate team entries. Export round-trips the six stored bytes. The punter and actual LS remain positional depth assignments.

DESIGN: KR1/KR2/PR use existing player lock bits 2/3/4. K and P rank zero and LS center rank one use rank locks. Swapping LS with the previous backup center preserves center rank zero and all offense/defense starters. No executable instruction, rating, contract, equipment, name, position or team membership is authored by dc.

DESIGN: retail celebrity/alumni/Pro Bowl rosters share the same player records as NFL clubs. Independent club returner locks therefore create unavoidable duplicate claims in those exhibition views. The validator retains the full conflict diagnostics, but does not reject a club import solely for a duplicate in a team numbered 32+ when every conflicting record also belongs to an NFL club. Conflicts within NFL clubs, and conflicts involving exhibition-only records, still refuse. Independent exhibition specialist assignments are outside this delivery.

DESIGN: CLE KR2 is KC Concepcion, the first available distinct PR entry after Dylan Sampson is missing. DAL KR2 is Caleb Downs after Malik Davis is missing. DEN LS retains Alex Forsyth because Mitchell Fraboni is missing. NO has neither Cal Adomitis nor Zach Wood and has no backup center; its existing native fallback selects tackle Will Sherman. NO's LS chart row remains empty. Exact NFL LS coverage is therefore 30/32, and exact source-list KR2 coverage is 30/32. These two LS gaps require a later roster-owner addition to become accurate.

## PROVED OFFLINE: ownership and replay

PROVED OFFLINE: the fragment has 223 player entries and six explicit role slots on each of 32 teams. It changes 382 ROST bytes, restricted to rank bits, existing lock bits and the six team index bytes. Every other bit of the complete ROST is identical: the before/after masked SHA-256 is `70287c1676880efe6bc59415d41d15cff02259d42fc0559ac5ecac8269d9091a`. Tests separately compare every other player field, names, membership, existing lock bits and offensive center starters.

PROVED OFFLINE: the merged JSON preserves every byte of C's original 3,349,541-byte file. Only two insertions are made: append fragment edits to the edits array, and append the new specialist member. Removing those exact insertion spans reproduces C byte-for-byte. No original owner's JSON entry or metadata is rewritten. Both insertion offsets and sizes are recorded in import.json and checked by a test.

PROVED OFFLINE: C on retail, fragment on C, repeated fragment on its own result, and merged file on retail all return zero log lines. Repeating the fragment changes zero bytes. The merged file retains C's source-name rename sequence, so whole-merged-document replay means replay on its retail source; it is not a claim that C's entire rename sequence can be applied twice without old-name warnings.

PROVED OFFLINE: the ready merged file is `/media/noah/Storage/.b76-research/dc/astra-build/league_roster_edits_candC_dc.json`, SHA-256 `35d855af3921c42f93e4c525a2868a2294fbd6e5cc717eaf9f6b141a43ea8e2c`. Native ROST after hash is `e0dec4d7d37ffe85afc74aad342530597b829396cb19b89606d15925a9d24c2e`. The current replay implementation must accompany that fragment because older readers do not apply the new optional `special_teams` member.

## PROVED OFFLINE: native proof and starter comparison

PROVED OFFLINE: [native_probe.py](native_probe.py) runs the actual native loader, list builder, chart getter and picker against C before and after. It then executes C's unlocked auto-depth once and the revised auto-depth three times. All 224 revised specialist picks survive all three sorts. It uses actual native rating routines, not synthetic score stubs. A 32-club league count, healthy eligibility and no saved substitutions are explicit synthetic context. No game routine is substituted and no xemu is launched.

PROVED OFFLINE: [lineup_probe.py](lineup_probe.py) executes the complete eleven-slot native lineup routine for 288 special-team formations across 32 clubs, using retail books normalized by the existing depth-role pass. Every normal kickoff return and punt-return slot selects its intended player. Eighteen Onside Kick Return formations use the same player as KR1 and PR; native duplicate handling correctly puts the next returner in the PR-coded second slot. [Every lineup and selection reason](proof/lineups.json). Final-disc books must additionally pass this probe during full-build verification.

PROVED OFFLINE: the same complete-lineup check also covers [all 288 original C formations](proof/lineups_before.json). Every specialist matches the original native table except eleven Onside Kick Return second slots, where an already-used KR1/PR identity correctly advances to the next returner. The original normal-kickoff and punt-return selections in the table are therefore also proved in full eleven-player lineups.

PROVED OFFLINE: [starter_differences.csv](proof/starter_differences.csv) contains all 183 differences/missing entries for later work. [starters.json](proof/starters.json) retains all 749 comparisons: 566 match, 181 differ and two snapshot players are missing. Native starter chart reads are identical before and after dc. No offensive or defensive starter was changed. DESIGN: the three nflverse WR ranks are compared with X/Z/SLOT only as an ordering convention; this source does not prove their alignment roles.

INFERRED: these offline proofs predict the corresponding game lineup for the stated healthy context. Injuries, fatigue, saved formation substitutions, later trades, absent players, old franchise saves and actual ball placement can change who fields a kick. The data does not promise that KR1 catches every kickoff. Holder persistence is proved for these 32 single-punter rosters, not arbitrary future multi-punter rosters.

## DESIGN: validation, full build and main lab

PROVED OFFLINE: the regression run finished with 414 tests passed, eight failed and 405 subtests passed in 4,304.13 seconds. All 172 roster/depth/special-role tests, including eleven dc tests, and all 119 memory-write gate tests passed. The cave-reference gate passed 123 tests; its eight failures repeat the same two kickoff-hook and practice-squad span assertions across four installation variants. [Counts and exact failing cases](proof/regression.json), [complete log](proof/regression.log).

PROVED OFFLINE: both failing assertions also reproduce on an untouched `git archive` of integrated base `9de33371`, without this job's code. That isolated baseline run finished with two failures in 341.90 seconds. Its scratch archive was deleted after preserving [the baseline receipt](proof/baseline_gates.json) and [exact failure log](proof/baseline_gates.log).

PROVED OFFLINE: the integrated manifest declares anniversary-kickoff ownership on the five kickoff hooks and franchise-economy/roster-fill ownership at `0x3D161F..0x3D162A`; these names are excluded by the failing assertions. [Manifest observations](proof/gate_manifest_observations.json). INFERRED: these are stale gate expectations in the integrated stack. This job changes neither those gate files nor those executable owners, and does not claim the complete cave-reference gate is green.

DESIGN: [build_full.py](build_full.py) copies C's recipe and frozen project byte-identically, overrides only the roster via the original full builder's CLI, waits for 30 GiB on Storage and more than 100 GiB on NVMe, then launches at nice 10 on cores 0-23. It acquires C's existing shared build/lab lock through a read-only descriptor and rechecks the space floors before calling the builder. All task staging, source-cache and output paths are under dc/astra-build. [finish_build.py](finish_build.py) reads the final disc roster/XBE, checks zero-log byte-exact fragment replay, reruns native and full-lineup proof against final books, verifies the build's disc hash, and deletes only the verified dc disc.

DESIGN: the full-build receipt and final validation results will be appended here after completion. The current task does not claim a finished build before those receipts exist.

PROVED OFFLINE: at 2026-09-28 14:13:52 UTC, the launcher had waited 105 minutes and Storage had 23,422,316,544 bytes free, about 21.81 GiB. The required start threshold is 30 GiB. NVMe had 113,835,253,760 bytes free, above the 100 GiB floor. This job's entire Storage output directory uses only 6.1 MiB, so local cleanup cannot close the gap. No task disc has been built. [Explicit pending-build receipt](proof/build_wait.json).

DESIGN: [main's three-kickoff lab script](lab/LAB_SCRIPT.md) targets ARI, DET and MIN, records the LAST PLAY `Kickoff returned by ...` card and includes a text checker. The third case includes franchise auto-depth and save/reload. The script is handed to main; no lab has been executed by Astra.

PROVED OFFLINE: there is no AGENTS.md in the supplied worktree. The parent `/home/noah/AGENTS.md`, project index, Desktop workspace AGENTS.md, START_HERE.md, AI_HANDOFF.md, the requested historical reports and depth-role memory were read. The explicit dc worktree/scope instructions supersede stale handoff locations. The Jev testing skill was read, but its status call was rejected by automatic approval review because this session's approval policy is never. No Jev result is claimed; direct native execution and deterministic checks supply the evidence.

## DESIGN: delivery and remaining build prerequisite

PROVED OFFLINE: the implementation and completed proofs are in the private Git repository `.scratch/dc.git`, based on `9de333712be81d919359131c2ecb2bd3185ac18a`. Commits use explicit pathspecs and the required Astra co-author trailer. The verified bundle is `/media/noah/Storage/.b76-research/dc/astra-build/b76-dc.bundle`; its tip, hash and verification output are in the adjacent `bundle_receipt.json`. Shared Git metadata was left unchanged.

DESIGN: main must free at least 9 GiB on Storage for the pending full build. The current launcher updates `dc/astra-build/build_execution.json` about every 15 seconds while queued, then waits for the existing shared build/lab lock. Check that live receipt before starting another launcher. The launcher already calls `finish_build.py` after a successful build; that verifier writes `full_build.json`, `final_native.json` and `final_lineups.json` under `dc/proof`, then deletes its verified task disc. Those final results still need to be incorporated into this report and the private bundle after they exist. The full-build requirement remains incomplete at this handoff.

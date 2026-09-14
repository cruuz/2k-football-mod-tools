# Beta 69 A1b: independent game integration audit

Audit branch: `astra/b69-a1b-audit-game`, from `c2489fcadfe412e0ed0afe20d8654bdc3170bba2`
(`local/stack-beta-69`, A2b landed). Ten findings are fixed. All four final XBE gates and the
34-test beta-68 Supersim live suite pass on stable final sources. Of 217 required standalone
files, 197 exit successfully (including their reported skips); 20 fail on absent local evidence.
C1 remains a documented contract conflict: the literal stronger clock exclusion is not satisfied
and the J5 WIRING behavior is preserved. No A1 studio-side implementation audit was repeated;
its report is absent from the audited head.

## Findings

| ID | Job | Hunk / defect | Verdict | Fix and evidence |
| --- | --- | --- | --- | --- |
| D1 | J5/A2b | Build and Gameplay source-state handling retained Modern CPU scrambles when switching away from an installed disc, including disabled foreign/unknown selectors. | PROVED product defect; WIRING omitted a source-transition reset. | Reset from the newly inspected source before saved-project restoration. Added `test_b69_a1b_game_audit.py`: six failing transition cases before the fix, then both tests pass, including linked panels and saved-project restore. |
| D2 | J3/J4/J5/A2b | Shared registry/catalog migration omitted the beta-68 audit's four 165/92 pins. | PROVED test-contract defect. | Update to 172/99; preserve execution of actual production assertions. `test_b68_a1_audit.py` failed before and passes after. |
| D3 | J5/A2b | Older caption suite required <=60 characters and obsolete Retail/Patch help words, rejecting J5's exact 61-character CPU-only caption. | PROVED test-contract defect. | Assert the exact J5 caption/help and CPU-only/Off/UNWITNESSED requirements; retain older checks for every other row. `test_beta62_integration3_qt.py` failed before and passes after. |
| D4 | J5/A2b | Complete-owner RX/RW totals, scaleout free-space pins and the published allocator request fixture omitted seven J5 requests. | PROVED test-contract defect. | Add the exact seven requests; use allocator-computed totals and alignment costs. Preserve capacity, permissions, legacy address equality, corruption and reverse-order assertions. Before logs retained; all 42 tests across the three affected suites pass after. |
| D5 | A2b report | Its protected-wiring table claims a climate Clear control and counts 12 entries in an 11-entry B69 runtime-pin block. | PROVED report overstatement, not a missing WIRING requirement. | Added a two-case failing report-contract regression. Correct the original report: the checkbox turns the climate plan off; the B69 block has 11 entries (studio has its separate pre-existing pin). |
| D6 | J3/J4/A2b | Beta-69 changelog and weather research still pointed to generic ASTRA_REPORT.md / WIRING.md after the handoffs were renamed. | PROVED documentation defect; new registry evidence paths themselves are correct. | Added a failing handoff-path regression and retargeted the current beta-69 references to ASTRA_B69_J3_REPORT.md / WIRING_B69_J4.md. Historical release notes are preserved. |
| D7 | J3/A2b | Franchise-2026's save-ownership description still declared prospect byte 83 reserved zero, and older native/host tests rejected now-valid caller/tier values. | PROVED ownership-description defect; the J3 codecs were already correct. | Added a failing contract/codec consistency test; describe byte 83 as tier-owned, keep reusable bytes zero and 88..127 reserved. Test all 15 valid caller/tier pairs and reject policy 3, bit 7, conflicting Supersim bits, tier 5 and reserved-byte writes. No native instruction or allocation changed. |
| D8 | J4/J5/A2b | ESPN panel test still asserted that its row was the only informational row. | PROVED test-contract defect. | Expect the climate action and scramble enum too; preserve the ESPN image gate, navigation and non-boolean plan assertions. Full 13-test suite passes. |
| D9 | J4 | A large integer in climate-plan JSON raised uncaught `OverflowError` before the field's range validator, escaping `status()` and Build's `ValueError` handling. | PROVED input-validation defect in the job's own writer. | Add a failing test covering all three draft fields and JSON before/after values, positive and negative. Check numeric bounds before float conversion. Ten failing subcases before; full 12-test file passes after. |
| D10 | J5/A2b | The exhaustive BuildPlan-to-control test omitted all three new combo bindings and repeated the obsolete 60-character coin-caption restriction (D3). | PROVED test-contract defect; the controls are present and connected. | Include the actual bindings, exercise non-default values through `plan()`, and preserve the exact CPU-only caption while keeping the length gate on other boxes. Existing suite fails twice before; all seven tests pass after. |
| C1 | J5 contract | Decided clock with accelerated clock installed can zero a qualifying Q4 game timer at 60 seconds. | Matches WIRING; does not satisfy the brief's literal stronger two-minute exclusion. | Preserve the documented cutoff contract and flag the conflict for Claude/Noah. The existing native pair test proves the counterexample; no claim is made that the literal exclusion passes. See the clock section below. |

## Reconstruction

The audit derives changes from Git objects, independently of A2b's own evidence ledger:

- J4 `f0d1ab53` -> merge `8cf389e6`; J3 `68b3818b` -> merge `54f5b8c8`;
  J5 `9afe21c0` -> merge `b5949335`.
- Per-job native/merge differences, full job-owned tip-to-stack patches and remerge conflict
  resolutions are under `reports/b69_a1b/j{3,4,5}-*.patch`.
- [Full integration patch](reports/b69_a1b/integration-full.patch) compares the merged job union
  `b5949335` to A2b's final head `c2489fca`. [Every-hunk ledger](reports/b69_a1b/integration-hunks.md)
  assigns a verdict to all 339 hunks in 208 files, including generated evidence additions.
- [Registry field deviations](reports/b69_a1b/registry-deviations.json) list every proposed/integrated
  JSON difference: renamed evidence, completed-integration wording, removal of completed porting
  tasks, saved-choice notes, and J4 module-form validation commands.
- At A2b's head, all native J3/J4/J5 game sources are byte-identical to the job tips. J3's changed shared provider
  pins and handoff JSON are integration differences, not native runtime modifications.

Applied exactly: new BuildPlan defaults and all three preset dictionaries; haze/rule XBE predicates;
climate data-only behavior; availability and inspect projections; rule REQUESTS selection and R62
space/runtime keys; explicit Retail enum deferral; final rule owner order immediately after accelerated
clock; J3 page controls and depth-lock dependencies; J4 climate/haze source checks and final writer order;
CPU-only caption; absence of a time-of-day toggle; release allowlist and specified shared count sites.

Documented adaptations: explicit saved FEATURE_KEYS (the existing serializer does not infer all
dataclass fields); shared Build/Gameplay synchronization and weather navigation; complete-plan
installed-setting preflight followed by private deferred passes; unchanged intermediate replay;
common rules helper excluded from double recorder attribution while each calling owner stays
observed; runtime pin/import and actual-panel checks; canonical registry wording and module commands.
The hunk ledger gives each exact insertion. [Audit fix patch](reports/b69_a1b/audit-fixes.patch) shows the resulting source, test, pin and documentation changes.

## Independently checked contracts

[Machine-readable contracts](reports/b69_a1b/contract-audit.json): 172 shared registry rows, 99 2K5
capabilities, 280 unified provider pins (all hashes match), 840 allowlist entries, 245 product imports,
35 tool imports. There are 11 entries in `B69_GAME_RUNTIME_PINS`; the separately updated studio pin
makes 12 additional/changed runtime dependency pins in A2b's description. Every new registry evidence
path exists here. All seven validation commands are module-form without arguments; all new runtime
statuses remain `not-tested` and GUI defaults false.

The excluded exhaustive validator is a separate older policy: `EXPECTED_CAPABILITIES=108`,
covered=103, deferred=5 and unique validators=83 in `tools/validate_all_mod_editor_capabilities.py`.
That entire tool predates the game integration. It is not a corrected 172-row release pin. Its current
test first fails on the known unreviewed module arguments. The parser-only inventory also records
15 older APF `packaging.*` rows outside that tool's accepted module prefixes; all 17 rejected rows
predate A2b. These existing validator-policy failures remain outside the requested game fixes.

J5 adds 7 requests: 896 RX + 4 RW + 140 RO bytes. The complete union has 64 allocations and a
12,300,288-byte extent. J3 retains 20,480 RX and two 4,096-byte RW blocks. J4 climate and haze have
empty REQUESTS; haze owns the full four-byte coefficient at `0xA867F4` in `.data`. Its reader/table
guards and complete ownership reservation were reviewed. No runtime data was moved into `.text`.

J5's shared writer validates each owner's exact allocation geometry, zero-initialized runtime state,
compiled instructions and padding, option bytes, every hook, and normalized retail prerequisite
digests. It refuses mixed installation and changed installed settings before mutation. CPU scrambles
accepts the excluded defensive-try neighbor only after verifying that entire owner. The standalone
rules suite exercises both application orders, resealed corruption, wrong settings, idempotence,
exclusive CLI output, and RX/RW/RO permissions. Its 16 tests pass on this tree.

The native coin proof covers both human sides, both toss outcomes, kick/receive choices, second-half
possession, all 17 RNG buckets, and overtime reset. Human-winner results match retail. The clock proof
covers leading/trailing possession, the margin/time boundary, live-play exclusion, quarters 3/5/6,
non-scrimmage phases, paused/count-up clocks and invalid floating-point times. The native series also
enters through the real dead-ball path. The scramble proof preserves human/non-QB/non-live behavior
and the timer/attempt gates; identical eligible inputs produce 21 versus 41 branch hits in 100 trials.
That is not a measured per-game scramble rate.

J3's save contract assigns caller policy to bits 5..6 of byte 82 and tier to byte 83. Policy zero keeps
the previous retail-position eligibility. The hand-back latch is transient: it is reset on load and
postgame and is never encoded as a preference. The fix reopens the native call screen only at the
guarded, unsnapped hand-back, retaining the binder's body control. The test ledger separately records
host/native setting round trips, the new hand-back series and the beta-68 Supersim live suite.

## Clock wording conflict

The brief says the decided-clock rule must never act inside accelerated clock's final two minutes.
Literally applying that exclusion to decided clock would disable every J5 cutoff (15, 30, 60, 90 or
120 seconds), including its required 60-second default. J5's WIRING explicitly specifies an independent
Q4 convenience cutoff and says accelerated clock keeps its own rules. This audit preserves that
contract: accelerated clock itself must skip the final two minutes, while the separately selected
decided rule can end a qualifying leading possession there. This is an explicit interpretation of
conflicting requirements, not proof of the literal stronger exclusion. The report does not claim it.

## Completed verification

All standalone runs use `PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONHASHSEED=0`.
The [inventory](reports/b69_a1b/inventory.json) includes job-changed suites, direct importers, older
`*_test.py` developer suites and their dynamic CI wrapper, the named wiring/packaging/provider suites,
and the MyCareer/Supersim series. [The test ledger](reports/b69_a1b/test-ledger.md) lists the exact
`python3 <file>` command result and full output for every required file. Its JSON retains every attempt,
log hash, source fingerprint and projection selection. Three job-added support modules also pass
standalone import checks; those zero-test imports are recorded separately. Non-test profiling/driver
scripts are not counted as test suites. No test result was substituted from A2b.

**Final native gates and regression:**

| Standalone file | Exact result | Output |
| --- | --- | --- |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | Ran 29 tests in 374.766s; OK (skipped=1) | [log](reports/b69_a1b/gates-after-climate/test_nfl2k5_cave_oracle.log) |
| `tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | Ran 506 tests in 2712.982s; OK | [log](reports/b69_a1b/gates-after-climate/test_nfl2k5_owner_pairwise_composition.log) |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | Ran 131 tests in 1764.508s; OK | [log](reports/b69_a1b/gates-after-climate/test_xbe_patch_cave_references.log) |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | Ran 119 tests in 1564.983s; OK | [log](reports/b69_a1b/gates-after-climate/test_xbe_patch_memory_writes.log) |
| `tests/mod_editor/test_nfl2k5_supersim_live.py` | Ran 34 tests in 2605.040s; OK | [log](reports/b69_a1b/supersim-final/test_nfl2k5_supersim_live.log) |

All five final native runs have identical start, end and current application-source hashes.
The 506-case pairwise suite includes J4 haze, all three J5 owners and the MyCareer owners, tests
both application orders and the complete selected union, and detects no owner collision. The oracle
has one explicit skip: the scratch manifest proves XBE composition and does not carry resource-build
evidence. That skipped case is not claimed as proved.

**Requested wiring and registry checks:**

| Standalone file | Exact result |
| --- | --- |
| [`test_beta66_d1_panels.py`](reports/b69_a1b/baseline/test_beta66_d1_panels.log) | Ran 4 tests in 1.521s; OK |
| [`test_discord_bugs_1_wiring.py`](reports/b69_a1b/final-stability/test_discord_bugs_1_wiring.log) | Ran 10 tests in 2.452s; OK |
| [`test_discord_bugs_2_wiring.py`](reports/b69_a1b/baseline/test_discord_bugs_2_wiring.log) | Ran 6 tests in 0.774s; OK (skipped=2) |
| [`test_2k5_build_is_explainable.py`](reports/b69_a1b/climate-integer/test_2k5_build_is_explainable.log) | Ran 16 tests in 0.018s; OK |
| [`test_capability_registry_module_commands.py`](reports/b69_a1b/baseline/test_capability_registry_module_commands.log) | Ran 3 tests in 0.001s; OK |
| [`test_product_catalog.py`](reports/b69_a1b/baseline/test_product_catalog.log) | Ran 9 tests in 0.047s; OK |
| [`test_provider_integrity.py`](reports/b69_a1b/baseline/test_provider_integrity.log) | Ran 7 tests in 8.515s; OK |
| [`test_providers.py`](reports/b69_a1b/baseline/test_providers.log) | Ran 33 tests in 3.658s; OK |
| [`test_phase1_packaging.py`](reports/b69_a1b/baseline/test_phase1_packaging.log) | Ran 23 tests in 0.080s; FAILED (errors=1) |

The 20 remaining failures are enumerated with exact tracebacks in
[environment-failures.json](reports/b69_a1b/environment-failures.json): 18 need missing `reports/assets`
metadata, one needs `docs/research/apf_audio.md`, and `test_apf_studio_installer.py` needs the absent
`tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md`. The installer failure here occurs at that
missing file, not at Capstone. `test_phase1_packaging.py` runs 23 tests and has one error for the missing
`reports/assets/menu_state_trace.json`. No placeholder evidence was fabricated. The additional excluded
`test_validate_all_capabilities.py` runs 36 tests and retains its older command-policy error, as described above.

Earlier source-overlap manifest refusals and the initial 2,400-second pairwise/Supersim timeouts remain
in the ledger. Stable reruns with a sufficient limit supersede them. Every proved fix has a failing
regression or existing failing contract suite recorded before correction;
[regression-evidence.json](reports/b69_a1b/regression-evidence.json) maps each finding to its before/after logs. The added product/ownership
regressions and every touched test file pass after the fixes.

The three assembly checks also pass: `python3 tools/mycareer_mode/build_runtime.py --check`,
`python3 tools/nfl2k5_my_career_assemble.py --check`, and `python3 tools/nfl2k5_rules_assemble.py --check`.
Their logs are `reports/b69_a1b/assembly-{runtime,binder,rules}.log`.

## Projection, scope and handoff

The final projection was regenerated by `test_nfl2k5_playbook_pair_manifest.py`: **Ran 1 test in
343.196s; OK**, with 137 observed XBE transactions and 12,548 reservations. All 331 source fingerprints
match the final tree. [Final verification](reports/b69_a1b/final-verification.json) records its hash.
The native composed output remains
`d570346339ca5a536be70812df154584d2ccbdd96e2ba180c28ccf7493033aa6`, exactly A2b's output.
The private retail XBE remains
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.

To reproduce the projection and gates after importing the bundle:

```bash
export PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONHASHSEED=0
mkdir -p .scratch/a2b
NFL2K5_PLAYBOOK_PAIR_MANIFEST="$PWD/.scratch/a2b/gate-manifest.json" python3 tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py
export NFL2K5_CAVE_MANIFEST="$PWD/.scratch/a2b/gate-manifest.json"
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_xbe_patch_cave_references.py
python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py
python3 tests/mod_editor/test_nfl2k5_supersim_live.py
```

The production `data/nfl2k5_cave_reservations.json` is unchanged. Claude must regenerate it after this
bundle lands, and run release packaging with its evidence files present. C1 needs a contract decision;
no stronger two-minute exclusion is claimed. The player witnesses in the J3/J4/J5 research reports
remain outstanding: rendered menus, physical hand-backs/kickoffs, weather appearance, clock/postgame
flow, scramble rates and full-game outcomes are **UNWITNESSED**. Native instruction and offline writer
results are **PROVED only within their declared harness seams**. No hypothesis is presented as a played result.

No xemu/Xenia, GUI display, audio output, network or full-disc copy was used. Root space began at
76 GiB available, below the context's full-disc-copy floor; the work used bounded executable and
synthetic fixtures. Private retail data is excluded from the bundle.

## Delivery

The shared Git directory was already read-only. Commits use the writable store recorded in
`reports/b69_a1b/git-store.json`, with original objects as read-only alternates. Implementation commits
are `407b25e1`, `f2bc9c02`, `1eb8f386` and `adc7ec3f`, followed by the final evidence/report commit.
`packaging/repin.py --apply` is the final content operation before every explicit-path commit.

`ASTRA_A1B.bundle` contains branch `astra/b69-a1b-audit-game` and requires
`c2489fcadfe412e0ed0afe20d8654bdc3170bba2`. `reports/b69_a1b/bundle-delivery.py` creates it, runs
`git bundle verify`, fetches into an independent Git store with only the original prerequisite objects,
and byte-compares every changed file with the committed worktree. Its post-commit receipt is written
alongside the bundle at `reports/b69_a1b/bundle-verification.json`.

```bash
git bundle verify ASTRA_A1B.bundle
git fetch ASTRA_A1B.bundle astra/b69-a1b-audit-game
```

`ASTRA_DONE` is written last, after bundle verification.

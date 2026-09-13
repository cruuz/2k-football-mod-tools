# Beta 69 A1b: independent game integration audit

Audit branch: `astra/b69-a1b-audit-game`, from `c2489fcadfe412e0ed0afe20d8654bdc3170bba2`
(`local/stack-beta-69`, A2b landed). This intermediate commit records the independently
reconstructed integration and first fixes. The final revision will include the completed
standalone test ledger, gate results and bundle instructions. No A1 studio-side implementation
audit was repeated; its report is absent from this head.

## Findings so far

| ID | Job | Hunk / defect | Verdict | Fix and evidence |
| --- | --- | --- | --- | --- |
| D1 | J5/A2b | Build and Gameplay source-state handling retained Modern CPU scrambles when switching away from an installed disc, including disabled foreign/unknown selectors. | PROVED product defect; WIRING omitted a source-transition reset. | Reset from the newly inspected source before saved-project restoration. Added `test_b69_a1b_game_audit.py`: six failing transition cases before the fix, then both tests pass, including linked panels and saved-project restore. |
| D2 | J3/J4/J5/A2b | Shared registry/catalog migration omitted the beta-68 audit's four 165/92 pins. | PROVED test-contract defect. | Update to 172/99; preserve execution of actual production assertions. `test_b68_a1_audit.py` failed before and passes after. |
| D3 | J5/A2b | Older caption suite required <=60 characters and obsolete Retail/Patch help words, rejecting J5's exact 61-character CPU-only caption. | PROVED test-contract defect. | Assert the exact J5 caption/help and CPU-only/Off/UNWITNESSED requirements; retain older checks for every other row. `test_beta62_integration3_qt.py` failed before and passes after. |
| D4 | J5/A2b | Complete-owner RX/RW totals, scaleout free-space pins and the published allocator request fixture omitted seven J5 requests. | PROVED test-contract defect. | Add the exact seven requests; use allocator-computed totals and alignment costs. Preserve capacity, permissions, legacy address equality, corruption and reverse-order assertions. Before logs retained; full post-fix suites running. |
| D5 | A2b report | Its protected-wiring table claims a climate Clear control and counts 12 entries in an 11-entry B69 runtime-pin block. | PROVED report overstatement, not a missing WIRING requirement. | Added a two-case failing report-contract regression. Correct the original report: the checkbox turns the climate plan off; the B69 block has 11 entries (studio has its separate pre-existing pin). |
| D6 | J3/J4/A2b | Beta-69 changelog and weather research still pointed to generic ASTRA_REPORT.md / WIRING.md after the handoffs were renamed. | PROVED documentation defect; new registry evidence paths themselves are correct. | Added a failing handoff-path regression and retargeted the current beta-69 references to ASTRA_B69_J3_REPORT.md / WIRING_B69_J4.md. Historical release notes are preserved. |
| D7 | J3/A2b | Franchise-2026's save-ownership description still declared prospect byte 83 reserved zero, and older native/host tests rejected now-valid caller/tier values. | PROVED ownership-description defect; the J3 codecs were already correct. | Added a failing contract/codec consistency test; describe byte 83 as tier-owned, keep reusable bytes zero and 88..127 reserved. Test all 15 valid caller/tier pairs and reject policy 3, bit 7, conflicting Supersim bits, tier 5 and reserved-byte writes. No native instruction or allocation changed. |
| D8 | J4/J5/A2b | ESPN panel test still asserted that its row was the only informational row. | PROVED test-contract defect. | Expect the climate action and scramble enum too; preserve the ESPN image gate, navigation and non-boolean plan assertions. Full 13-test suite passes. |
| D9 | J4 | A large integer in climate-plan JSON raised uncaught `OverflowError` before the field's range validator, escaping `status()` and Build's `ValueError` handling. | PROVED input-validation defect in the job's own writer. | Add a failing test covering all three draft fields and JSON before/after values, positive and negative. Check numeric bounds before float conversion. Ten failing subcases before; full 12-test file passes after. |

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
- All native J3/J4/J5 game sources remain byte-identical to the job tips. J3's changed shared provider
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
The hunk ledger gives each exact insertion, rather than attributing other stack jobs to A2b.

## Independently checked contracts

[Machine-readable contracts](reports/b69_a1b/contract-audit.json): 172 shared registry rows, 99 2K5
capabilities, 280 unified provider pins (all hashes match), 840 allowlist entries, 245 product imports,
35 tool imports. There are 11 entries in `B69_GAME_RUNTIME_PINS`; the separately updated studio pin
makes 12 additional/changed runtime dependency pins in A2b's description. Every new registry evidence
path exists here. All seven validation commands are module-form without arguments; all new runtime
statuses remain `not-tested` and GUI defaults false.

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

## Evidence scope and remaining work

Standalone runs use `PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONHASHSEED=0`.
The [inventory](reports/b69_a1b/inventory.json) includes job-changed tests, tests importing changed
application/test-support modules, all requested named suites and the MyCareer/Supersim series.
Every file runs in a separate Python process; logs and source fingerprints are retained.

The observed projection was freshly regenerated at `.scratch/a2b/gate-manifest.json` by
`test_nfl2k5_playbook_pair_manifest.py`: `Ran 1 test in 325.472s`, `OK`, 137 XBE transactions and
12,548 reservations. Its 331 source fingerprints match this tree. The production manifest remains
unchanged; Claude must regenerate it after this bundle lands. The four gates are still running.

No emulator, display, audio, network or full-disc copy was used. The root began at 76 GiB available,
below the context's full-disc-copy floor; work uses bounded private executable/synthetic fixtures.
Native instruction and offline writer proofs are PROVED only within their declared harness seams.
Rendered game behavior, physical plays, frame/audio cadence and player-visible outcomes remain
UNWITNESSED. Hypotheses are not promoted to defects without a failing executable test.

The shared Git directory is already read-only. Commits use the writable store identified in
`reports/b69_a1b/git-store.json`, with original objects as read-only alternates, through `/tmp/a1b-git`.
The final portable delivery will be `ASTRA_A1B.bundle`. Repin is the last content operation before
each explicit-path commit. `ASTRA_DONE` will be written last after bundle verification.

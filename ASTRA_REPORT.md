# b72-m1: MyCareer host-side preparation

Base: `088e3f4120e2413a136fd438f116a793901f3b3c`.
Delivery branch: `b72-m1` in `.scratch/b72-m1-delivery.git`.
Bundle: `.scratch/astra-b72-m1.bundle` (verified after final validation).

## Implemented

- All proposed scoring tables and the 21-row Max Speed chart, validated on import. Decimal half-up hundredths close time gaps; rounded ties select the first attempt; speed clamps to 75/95 outside the chart. Senior Bowl credits cap at six and pre-draft credits at eleven. Completion percentages use continuous thresholds and negative yards earn zero.
- Earned purchases debit event-specific attribute buckets through existing progression caps. Speed also obeys the dash ceiling. SCR remains excluded because existing progression reserves its style/parity byte. Purchases only increase ratings. Results are supplied host-side; no playable event or automatic stat collection is claimed.
- A replay-checked journal recomputes all credit and spending. Unique event slots and transaction IDs prevent replay; exact record matching prevents stale-record purchases. Standalone saves lock and atomically replace the file, refusing a journal that would roll back spending. Named and recovery Studio projects retain the same journal. Failed writes and imports restore prior state. Studio reports project-storage failures while preserving the prepared journal file.
- Jersey, height, weight and college controls on creation. Body fields precede tier calibration, and the serialized player is read back. All 612 native-template/body/tier combinations passed at 74/70/64/59. Signed preparation also now accepts its own prospect metadata during setup read-back.
- The design's eleven positions in proposal order with retail pools, or ten with LB and no OLB under one-pool mode. Native API compatibility still accepts the seventeen retail codes. QB has a real host-authored fourth Gunslinger vector: arm 95, accuracy 78, reads 72, with Pocket's other fields. Every other visible position has three templates. No native template row changes.
- Draft Advisory rereads the prepared save, rejects a changed class or mode, and ranks per-club target shortfalls and maximum headroom. Its source tables are the executable's existing 0x521C68/0x521C20 tables. Cut risk reports position rank and projected roster size against the 53-man limit, with incumbents winning rating ties. Both estimates are read-only and neither changes the draft nor cuts MyPlayer.

Detailed rules and API examples are in `docs/mod_editor/nfl2k5_my_career_events.md` and the module docstrings. The authorized Studio panel/shell wiring is implemented. Protected release-list and registry follow-up instructions are in `WIRING.md`; zero capability rows are added and no registry-count adjustment is needed.

## PROVED offline

`python3 reports/b72_m1/verify_host_only.py` compared both MyCareer XBE outputs to the base module and found byte identity. It also checked the b69 budget byte-for-byte. The receipt is `reports/b72_m1/host_only.json`.

- MyCareer default XBE SHA-256: `f22244ea9bf38adcb365b49e85c64fd6dd8e434e98ba72c9020d87b29803e1fe`.
- MyCareer mode XBE SHA-256: `1b44fa969ad242b9146bed47c6a0dbe1d94ec600e42a1e24d2b4703f657ad436`.
- Unchanged b69 budget SHA-256: `738619010952184b76b7a0bf5e811f352f353013119e7cd597c7d0c982d0dd73`.
- RX remains 20,480 bytes with 295 spare; menu capacities remain unchanged. No native source, progression-cap table, allocation or reservation changed.

The protected release manifest remains untouched. The proof script derives `.scratch/b72-m1-gate-manifest.json` by retaining every reservation/allocation and updating only the verified MyCareer source pin. Integration must regenerate the release manifest after all jobs land.

## Validation

The complete standalone run is `python3 reports/b72_m1/run_checks.py all`. It launches at most two detached test runners while retaining a supervisor because this tool sandbox reaps orphaned jobs. Each test process receives `PYTHONPATH=<worktree>`, `QT_QPA_PLATFORM=offscreen` and `NFL2K5_CAVE_MANIFEST=<worktree>/.scratch/b72-m1-gate-manifest.json`. Exact per-suite results and raw unittest output are in `reports/b72_m1/`.

The original creation suite initially failed because its old assertion still rejected a fourth QB template and expected the old error text. The updated assertion rejects QB slot four (the fifth slot); the complete 13-test suite passed on rerun. This is recorded separately in `test_nfl2k5_my_career-final.log`. The original runner retains its failure exit status; the final aggregate uses the complete passing rerun.

All 46 main and related standalone suites have completed: 276 tests, including four skips in `test_mycareer_art.py` because the private source cache for the composed backdrop is absent. The new host acceptance tests have no skips. The memory-write, cave-reference and cave-oracle gates passed 119, 131 and 29 tests respectively.

`python3 reports/b72_m1/summarize_checks.py` returned:

```json
{"status": "passed", "standalone_suites": 51, "tests": 1072, "skipped": 4}
```

That is 1068 passing tests and 4 explicitly skipped artwork-cache tests. All four XBE gates passed without skips:

| Standalone gate | Tests | Skips | Result |
| --- | ---: | ---: | --- |
| `test_xbe_patch_memory_writes` | 119 | 0 | Passed |
| `test_xbe_patch_cave_references` | 131 | 0 | Passed |
| `test_nfl2k5_cave_oracle` | 29 | 0 | Passed |
| `test_nfl2k5_owner_pairwise_composition` | 506 | 0 | Passed |

The 51-suite aggregate includes all 35 `test_nfl2k5_my_career*.py` files, eleven related build/project/art suites, the four XBE gates and the eleven-test position-choice suite. The new body test covers 612 template/body/tier combinations. Separate final targeted event and advisory checks also passed, as recorded in `aggregate.json`.

The corrected creation rerun command was `PYTHONPATH=<worktree> QT_QPA_PLATFORM=offscreen NFL2K5_CAVE_MANIFEST=<worktree>/.scratch/b72-m1-gate-manifest.json python3 tests/mod_editor/test_nfl2k5_my_career.py`; its output was `Ran 13 tests` and `OK`. The position-choice command used the same environment with `tests/mod_editor/test_nfl2k5_position_choices.py`; its output was `Ran 11 tests` and `OK`. The runner records every other standalone command in `run_checks.py` and every result in the matching log. No required failed result is omitted.

`python3 packaging/repin.py --apply` reported zero outstanding pin updates, and `git diff --check` passed.

## UNWITNESSED and boundaries

No game, xemu, Xenia or GUI display was launched. Native functions were exercised only in bounded offline harnesses. There is no playable pre-draft event, Pro Day flow, Senior Bowl game flow, native draft modification or career-ending preseason cut. No in-game result is claimed. The new controls and estimates need a user workflow check against a real prepared save; body appearance and the authored QB prototype need a played witness before making in-game claims.

The local journal validates bookkeeping, not the truth of supplied results or deliberate manual file rollback. Event spending APIs do not alter native career XP. The fourth QB vector is a Studio preparation template, not an extra slot in the native table.

## Git delivery and integration

The checkout's shared Git directory is read-only under the supplied sandbox, so `git switch -c b72-m1` was refused. A separate writable Git metadata directory inside this worktree borrows the original objects read-only. All delivery commits and the `b72-m1` branch live there; ordinary checkout metadata is untouched. The verified bundle carries only this job's commits and requires the stated base commit. No push was attempted.

Follow `WIRING.md` to package the two new host modules, extend the existing capability evidence and regenerate the release manifest. Existing source pins were refreshed with `python3 packaging/repin.py --apply`. Preset defaults remain unchanged.

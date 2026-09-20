# b72-s10 validation

All 35 default scorebug, provider-integrity and standalone packaging test files pass: 313 cases, 305 executed and 8 existing skips. Each file ran separately with plain Python, `PYTHONPATH` set to this checkout, `QT_QPA_PLATFORM=offscreen`, one worker and an enforced 100-second timeout. The slowest final file is the resource suite at 83.15 seconds. `checks/results.json` and its named logs are the final receipts.

```bash
python3 reports/b72_s10/run_checks.py
python3 reports/b72_s10/audit.py
python3 reports/b72_s10/run_closures.py
python3 reports/b72_s10/scan_owner.py
python3 reports/b72_s10/run_aux.py
python3 reports/b72_s10/scan.py
python3 packaging/repin.py --apply
```

The native raster label audit passes all 104 combinations: 52 current/historical native team slots, both aspects. It checks the preserved text readability floor and contrast, layout footprint and generated resource sizes. This is an offline label result, not a played witness. `readability.json`, `logo_fits.json`, `budgets.json`, and the two all-team grids retain the details. Native long-clock tests cover 9:59, 10:00 and larger clocks.

The retained Unicorn sequence run passes 675 frames per aspect, 1,350 total. Its actual captured material/event records cover pre-snap, punt/hang-time, after-play, FLAG, FUMBLE and down-label recovery. `native_sequences/sequences.json` and `retained_sequences.log` are the receipts. Existing native draw-order tests deliberately break submission order and ensure a hidden label cannot be rescued by a friendly preview. No game or emulator was launched.

The focused native owner scan passes 31 composition pairs in both orders, with writable destinations, RX/RW permissions, idempotence and hook ownership checked. The source manifest freshness check separately reports the inherited stale `nfl2k5_scorebug_exact.py` fingerprint. Native owner files and the protected manifest are byte-identical to base `97d2bf9b2`; source freshness is not claimed. The integrator must regenerate the manifest on the final stack as described in `../../WIRING.md`.

Broader auxiliary suites are separately bounded at 420 seconds each. A timeout is incomplete, not a pass. These suites cover the complete unrelated owner union in multiple installation orders; they are additional coverage beyond the unchanged scorebug owner and its focused 31-pair proof. Final recorded auxiliary results:

| Standalone file | Result | Seconds |
|---|---|---:|
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | INCOMPLETE: timeout | 420.03 |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | INCOMPLETE: timeout | 420.03 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | FAIL | 394.37 |
| `tests/mod_editor/test_phase1_packaging.py` | PASS | 2.48 |

The cave-oracle suite finishes 29 tests with two errors, both the inherited stale `nfl2k5_scorebug_exact.py` manifest fingerprint; 27 tests pass. The standalone phase-one packaging suite passes. The memory-write and cave-reference suites time out at 420 seconds, so their partial dot output is not counted as a suite pass. No native game code or these test files changed. The protected manifest remains an explicit integration requirement.

Both 2K5 and APF product closures pass staging, release inventory/integrity checks and isolated runtime checks. Staging directories were removed. `run_closures.py` records the exact commands; `closures.json`, `2k5_closure_*.log` and `apf2k8_closure_*.log` retain their results. APF shipping bytes are unchanged. Existing allowlists already contain every modified shipping path; no inventory entries, dependencies, capability rows or provider-count expectations were added.

The PNG catalogue records the exact final 22,990-byte PNG and SHA-256. The release checker changes only its catalogue hash constant; an AST comparison verifies all other checker logic is identical. Replication and provider pins match final source bytes. Deterministic asset regeneration is byte-identical (`author_roundtrip.json`); native runtime reproducibility passes (`runtime_reproducibility.log`). The append is 325,216 bytes at each aspect, below 400,000. RX remains 4,086 of 4,096 bytes, with 10 spare; RW remains 128 bytes. No native code was added.

`scans.json` verifies existing allowlist membership, unchanged native owners, official palette and provider-count tests, no credential-pattern hits, and no added em dashes. The product closure also performs its retained-byte policy audit. Only development evidence/scripts are added under this report directory.

Failed trials are retained, not erased: the initial wider source plate failed the SD footprint test, the old logo-ratio assertion used the previous well geometry, and closure attempts exposed stale PNG size/catalogue pins. The plate was prefiltered to 91x17, the logo contract now derives the actual quad aspect with unchanged tolerance, and exact catalogue pins were refreshed. `checks_before_sd_fix/`, `checks/sprite_initial.log`, and closure logs with `before_` in their names preserve those failures. Final default tests and closures pass after correction.

The visual metric has no all-clear threshold. Logo, wing, housing/rim and score area decrease; plate and pill show no material closure. `GAPS.md` reports every nonzero residual. The six final comparison sheets use the final corrected SD cell and include genuine supplied disc r before captures.

# b72-s11 validation

All 36 default standalone files pass: 316 test cases, 308 executed and 8 existing skips. Each file runs with plain Python, `PYTHONPATH` set to this checkout, `QT_QPA_PLATFORM=offscreen`, one worker and a 150-second bound. The set includes every scorebug suite, the new full-mark regression, provider integrity, replication pins and standalone packaging checks. Named logs and `checks/results.json` retain the exact results.

The all-team audit passes 64 primary-team/aspect containment checks at both ends, with exact 100 percent weighted and binary source-ink retention. All 104 native label measurements equal s10. Both full contact sheets and six player-scale before/after sheets are retained. The 1,350 retained event-frame records are identical to the parsed s10 records, covering pre-snap, punt/hang-time, after-play, FLAG, FUMBLE and down-label recovery. This is bounded native CPU and software-raster evidence only.

Both product closures pass all three steps: temporary staging, release inventory/integrity validation, and isolated runtime validation. Temporary stages are removed. The release inventories, provider counts, PNG catalogue, release checkers, runtime sources, palette fields and template PNG remain unchanged. Repin refreshes only the existing team-accent metadata digest. Appended size remains 325,216 bytes in both aspects, RX remains 4,086/4,096 bytes, and RW remains 128 bytes. Every component retains its byte size. Native runtime regeneration passes `build_runtime.py --check`.

The focused scorebug owner scan checks writable destinations, RX/RW permissions, idempotence and hook ownership, plus the 31 relevant owner-composition pairs in both orders. The source-manifest audit separately reports the inherited stale `nfl2k5_scorebug_exact.py` fingerprint. The protected manifest and all runtime owner sources are unchanged. Integration still requires the manifest regeneration documented in `../../WIRING.md`.

Broader auxiliary suites are bounded separately at 420 seconds each. These results are not counted as default-suite passes:

| Auxiliary suite | Result | Seconds |
|---|---|---:|
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | INCOMPLETE: timeout | 420.03 |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | INCOMPLETE: timeout | 420.04 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | FAIL | 368.20 |
| `tests/mod_editor/test_phase1_packaging.py` | PASS | 2.12 |

The cave-oracle suite completes 29 tests: 27 pass and two error on the same inherited stale source fingerprint, reported by `nfl2k5_cave_oracle.py:217`. The failing callers are `test_nfl2k5_cave_oracle.py:382` and `:395`. These are source-manifest freshness errors, not new runtime writes. No manifest-freshness pass is claimed.

The original sprite aspect test failure is retained in `sprite_old_cropped_aspect.log`: its expected Chiefs ratio described the cropped mark. The final test expects the complete silhouette, with the same tolerance and minimum aspect. The original cropped Washington, Texans, Raiders and Steelers fits are negative controls in the new regression. No integrity check or label threshold was weakened.

Exact command orchestration is in `validate.py`, `run_checks.py`, `run_closures.py`, `run_aux.py` and their progress receipts. The core reproduction commands are:

```bash
python3 reports/b72_s11/fit.py
python3 packaging/repin.py --apply
python3 reports/b72_s11/validate.py baseline final audit sheets events checks owner closures
python3 reports/b72_s11/run_aux.py
python3 tools/scorebug_sprite/build_runtime.py --check
python3 reports/b72_s11/finish.py
python3 reports/b72_s11/scan.py
```

No emulator, disc image build, publish, push or release action ran. A disposable product closure is validation only. GPU/display calibration and a played retest remain unwitnessed.

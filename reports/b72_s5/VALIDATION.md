# b72-s5 validation

**The GPU reproduction gate fails. No cause-specific dark-label fix or in-game witness is claimed.**

Required inventory: 34 standalone test files; exit-code gate PASS; default-path timing gate PASS (<100 seconds per file).
There are 298 collected cases: 290 execute and eight retain existing skips. Five skips cover superseded beta-69 private-font tests, one disc transaction cannot write its external scratch directory, and two source-art comparisons lack developer copies. Verbose reasons are retained in `checks_final/skip_detail_*.log`. No new skip was added.

The inventory includes all scorebug files, the five sprite suites, provider integrity, replication pins and both portability scans. Default commands are `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 <file>`; no speed switch or reduced scenario set is used.

| File | Tests | Skipped | Exit | Seconds | Log |
|---|---:|---:|---:|---:|---|
| test_apf_scorebug_workspace_qt.py | 11 | 0 | 0 | 1.37 | [log](checks/test_apf_scorebug_workspace_qt.log) |
| test_nfl2k5_scorebug_assets.py | 8 | 1 | 0 | 9.03 | [log](checks_final/test_nfl2k5_scorebug_assets.log) |
| test_nfl2k5_scorebug_author.py | 12 | 0 | 0 | 6.27 | [log](checks/test_nfl2k5_scorebug_author.log) |
| test_nfl2k5_scorebug_down_visibility.py | 2 | 0 | 0 | 30.26 | [log](checks_final/test_nfl2k5_scorebug_down_visibility.log) |
| test_nfl2k5_scorebug_draw_order.py | 5 | 0 | 0 | 16.59 | [log](checks_final/test_nfl2k5_scorebug_draw_order.log) |
| test_nfl2k5_scorebug_exact.py | 8 | 0 | 0 | 36.88 | [log](checks_final/test_nfl2k5_scorebug_exact.log) |
| test_nfl2k5_scorebug_fonts.py | 10 | 5 | 0 | 8.08 | [log](checks/test_nfl2k5_scorebug_fonts.log) |
| test_nfl2k5_scorebug_freeze.py | 7 | 0 | 0 | 39.87 | [log](checks_final/test_nfl2k5_scorebug_freeze.log) |
| test_nfl2k5_scorebug_freeze_v2.py | 7 | 0 | 0 | 65.77 | [log](checks_final/test_nfl2k5_scorebug_freeze_v2.log) |
| test_nfl2k5_scorebug_ingame.py | 11 | 0 | 0 | 7.48 | [log](checks_final/test_nfl2k5_scorebug_ingame.log) |
| test_nfl2k5_scorebug_ingame_fix.py | 9 | 0 | 0 | 54.86 | [log](checks_final/test_nfl2k5_scorebug_ingame_fix.log) |
| test_nfl2k5_scorebug_mnf.py | 10 | 0 | 0 | 14.62 | [log](checks/test_nfl2k5_scorebug_mnf.log) |
| test_nfl2k5_scorebug_mnf_v3.py | 7 | 0 | 0 | 55.11 | [log](checks/test_nfl2k5_scorebug_mnf_v3.log) |
| test_nfl2k5_scorebug_native.py | 4 | 0 | 0 | 44.49 | [log](checks/test_nfl2k5_scorebug_native.log) |
| test_nfl2k5_scorebug_projection.py | 14 | 0 | 0 | 54.70 | [log](checks_final/test_nfl2k5_scorebug_projection.log) |
| test_nfl2k5_scorebug_resources.py | 6 | 0 | 0 | 78.49 | [log](checks_final/test_nfl2k5_scorebug_resources.log) |
| test_nfl2k5_scorebug_runtime.py | 12 | 0 | 0 | 37.46 | [log](checks/test_nfl2k5_scorebug_runtime.log) |
| test_nfl2k5_scorebug_sd.py | 3 | 0 | 0 | 0.61 | [log](checks_final/test_nfl2k5_scorebug_sd.log) |
| test_nfl2k5_scorebug_source_art.py | 13 | 2 | 0 | 4.68 | [log](checks/test_nfl2k5_scorebug_source_art.log) |
| test_nfl2k5_scorebug_sprite.py | 19 | 0 | 0 | 41.58 | [log](checks_final/test_nfl2k5_scorebug_sprite.log) |
| test_nfl2k5_scorebug_template.py | 19 | 0 | 0 | 5.32 | [log](checks/test_nfl2k5_scorebug_template.log) |
| test_nfl2k5_scorebug_template_release.py | 5 | 0 | 0 | 0.57 | [log](checks/test_nfl2k5_scorebug_template_release.log) |
| test_nfl2k5_scorebug_unified_adapter.py | 5 | 0 | 0 | 0.21 | [log](checks/test_nfl2k5_scorebug_unified_adapter.log) |
| test_nfl2k5_scorebug_v10_ingame.py | 11 | 0 | 0 | 8.33 | [log](checks/test_nfl2k5_scorebug_v10_ingame.log) |
| test_nfl2k5_scorebug_v10_projection.py | 14 | 0 | 0 | 27.96 | [log](checks/test_nfl2k5_scorebug_v10_projection.log) |
| test_nfl2k5_scorebug_versions.py | 4 | 0 | 0 | 8.38 | [log](checks/test_nfl2k5_scorebug_versions.log) |
| test_nfl2k5_scorebug_watermark.py | 3 | 0 | 0 | 38.13 | [log](checks_final/test_nfl2k5_scorebug_watermark.log) |
| test_provider_integrity.py | 8 | 0 | 0 | 10.13 | [log](checks_final/test_provider_integrity.log) |
| test_scorebug_gpu.py | 9 | 0 | 0 | 17.84 | [log](checks_final/test_scorebug_gpu.log) |
| test_scorebug_replication.py | 12 | 0 | 0 | 0.52 | [log](checks_final/test_scorebug_replication.log) |
| test_scorebug_sprite_preview_qt.py | 3 | 0 | 0 | 12.78 | [log](checks/test_scorebug_sprite_preview_qt.log) |
| test_scorebug_studio_panel_qt.py | 11 | 0 | 0 | 7.33 | [log](checks/test_scorebug_studio_panel_qt.log) |
| test_shipped_tools_are_self_sufficient.py | 3 | 0 | 0 | 11.88 | [log](checks_final/test_shipped_tools_are_self_sufficient.log) |
| test_shipped_tools_posix_only.py | 13 | 0 | 0 | 11.58 | [log](checks_final/test_shipped_tools_posix_only.log) |

Results combine the full first run with later focused runs after performance changes. Earlier over-budget runs remain in `checks/results.json`, `checks_final/results.json` and progress logs. Only the latest applicable receipt is used above. [Performance changes and byte-equivalence evidence](PERFORMANCE.md) explain the optimizations.

Both application closures are audited in disposable temporary directories. Staging below is solely for closure checks; no installer, playable test disc or release is produced.

| Product | Check | Exit | Seconds |
|---|---|---:|---:|
| 2k5 | temporary stage | 0 | 0.31 |
| 2k5 | release closure | 0 | 7.03 |
| 2k5 | runtime closure | 0 | 11.98 |
| apf2k8 | temporary stage | 0 | 0.11 |
| apf2k8 | release closure | 0 | 0.42 |
| apf2k8 | runtime closure | 0 | 11.89 |

The native runtime rebuild check passes. Appended data is 324,832 / 400,000 bytes; RX is 4,086 / 4,096 bytes; RW reservation is 128 bytes. Only 10 RX bytes remain. [Budget receipt](budgets.json), [build check](build_runtime_final.log).

Auxiliary audits are reported separately:

- XBE space tests: PASS, 28.86 seconds.
- Cave oracle: FAIL, 29 tests with two stale reservation-source errors, 351.49 seconds including startup. Both errors first identify `mod_editor/core/nfl2k5_scorebug_ingame.py`. No manifest was regenerated, as instructed. The integrator must refresh reservations and rerun this audit after integration. [Log](checks_final/test_nfl2k5_cave_oracle.log).
- Allocator integration: the 420-second runner timed out; its longer retry is recorded below. This auxiliary file is outside the requested scorebug timing inventory. [Original timeout log](checks_final/test_beta61_allocator_integration.log).
- Allocator retry with a 900-second outer limit: exit 0, 431.67 seconds. [Log](checks_final/test_beta61_allocator_integration_retry.log). The retry does not erase the first timeout.

[24 quantizer and 264 panel differential comparisons](performance_equivalence.log) pass against `ec5d68d4`. The new GPU/palette suite checks packet decoding, the observed combiner, neutral masks, palette rejection, byte counters, cache invalidation, pinned logo isolation, all 52 native tint slots at both possessions/aspects and independent texture decode.

New modules are declared in the release allowlist and pinned via `packaging/repin.py --apply`. Provider closure is 301 entries. The template PNG catalog updates only the changed template hash/size and its digest pin. The supplied official colour dataset and cave manifest are unchanged.

The unavailable `/home/noah/ai-stack/jev/recipes/jev_diff_gate.py` was not run; the integrator owns that check. Hunk whitespace, added em dashes and Python syntax are checked separately. No cross-time ctime comparisons were added.

[GPU findings](GPU_FINDINGS.md), [calibration errors](calibration.json), [team-colour review](TEAM_COLOURS.md), [Jev requests and receipts](accents/responses.json).

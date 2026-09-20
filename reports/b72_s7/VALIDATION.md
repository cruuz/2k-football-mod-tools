# b72-s7 validation

All 35 inherited required standalone test files pass: 307 cases collected, 299 executed, 8 existing skips. No tests were added for this evidence-only change. All files finished below the existing 100-second limit.

| File | Cases | Skips | Seconds | Exit |
|---|---:|---:|---:|---:|
| [test_apf_scorebug_workspace_qt](checks/test_apf_scorebug_workspace_qt.log) | 11 | 0 | 1.52 | 0 |
| [test_nfl2k5_scorebug_assets](checks/test_nfl2k5_scorebug_assets.log) | 8 | 1 | 6.53 | 0 |
| [test_nfl2k5_scorebug_author](checks/test_nfl2k5_scorebug_author.log) | 12 | 0 | 6.43 | 0 |
| [test_nfl2k5_scorebug_down_visibility](checks/test_nfl2k5_scorebug_down_visibility.log) | 2 | 0 | 19.96 | 0 |
| [test_nfl2k5_scorebug_draw_order](checks/test_nfl2k5_scorebug_draw_order.log) | 5 | 0 | 9.19 | 0 |
| [test_nfl2k5_scorebug_exact](checks/test_nfl2k5_scorebug_exact.log) | 8 | 0 | 29.88 | 0 |
| [test_nfl2k5_scorebug_fonts](checks/test_nfl2k5_scorebug_fonts.log) | 10 | 5 | 4.82 | 0 |
| [test_nfl2k5_scorebug_freeze](checks/test_nfl2k5_scorebug_freeze.log) | 7 | 0 | 17.65 | 0 |
| [test_nfl2k5_scorebug_freeze_v2](checks/test_nfl2k5_scorebug_freeze_v2.log) | 7 | 0 | 33.83 | 0 |
| [test_nfl2k5_scorebug_ingame](checks/test_nfl2k5_scorebug_ingame.log) | 11 | 0 | 8.18 | 0 |
| [test_nfl2k5_scorebug_ingame_fix](checks/test_nfl2k5_scorebug_ingame_fix.log) | 9 | 0 | 56.97 | 0 |
| [test_nfl2k5_scorebug_mnf](checks/test_nfl2k5_scorebug_mnf.log) | 10 | 0 | 11.44 | 0 |
| [test_nfl2k5_scorebug_mnf_v3](checks/test_nfl2k5_scorebug_mnf_v3.log) | 7 | 0 | 21.61 | 0 |
| [test_nfl2k5_scorebug_native](checks/test_nfl2k5_scorebug_native.log) | 4 | 0 | 22.16 | 0 |
| [test_nfl2k5_scorebug_projection](checks/test_nfl2k5_scorebug_projection.log) | 14 | 0 | 26.82 | 0 |
| [test_nfl2k5_scorebug_resources](checks/test_nfl2k5_scorebug_resources.log) | 6 | 0 | 82.67 | 0 |
| [test_nfl2k5_scorebug_runtime](checks/test_nfl2k5_scorebug_runtime.log) | 12 | 0 | 13.5 | 0 |
| [test_nfl2k5_scorebug_sd](checks/test_nfl2k5_scorebug_sd.log) | 3 | 0 | 0.62 | 0 |
| [test_nfl2k5_scorebug_source_art](checks/test_nfl2k5_scorebug_source_art.log) | 13 | 2 | 2.07 | 0 |
| [test_nfl2k5_scorebug_sprite](checks/test_nfl2k5_scorebug_sprite.log) | 19 | 0 | 22.16 | 0 |
| [test_nfl2k5_scorebug_template](checks/test_nfl2k5_scorebug_template.log) | 19 | 0 | 5.07 | 0 |
| [test_nfl2k5_scorebug_template_release](checks/test_nfl2k5_scorebug_template_release.log) | 5 | 0 | 0.61 | 0 |
| [test_nfl2k5_scorebug_unified_adapter](checks/test_nfl2k5_scorebug_unified_adapter.log) | 5 | 0 | 0.21 | 0 |
| [test_nfl2k5_scorebug_v10_ingame](checks/test_nfl2k5_scorebug_v10_ingame.log) | 11 | 0 | 6.43 | 0 |
| [test_nfl2k5_scorebug_v10_projection](checks/test_nfl2k5_scorebug_v10_projection.log) | 14 | 0 | 26.36 | 0 |
| [test_nfl2k5_scorebug_versions](checks/test_nfl2k5_scorebug_versions.log) | 4 | 0 | 4.92 | 0 |
| [test_nfl2k5_scorebug_watermark](checks/test_nfl2k5_scorebug_watermark.log) | 3 | 0 | 17.65 | 0 |
| [test_provider_integrity](checks/test_provider_integrity.log) | 8 | 0 | 11.24 | 0 |
| [test_scorebug_gpu](checks/test_scorebug_gpu.log) | 9 | 0 | 9.18 | 0 |
| [test_scorebug_live](checks/test_scorebug_live.log) | 9 | 0 | 0.16 | 0 |
| [test_scorebug_replication](checks/test_scorebug_replication.log) | 12 | 0 | 0.52 | 0 |
| [test_scorebug_sprite_preview_qt](checks/test_scorebug_sprite_preview_qt.log) | 3 | 0 | 7.28 | 0 |
| [test_scorebug_studio_panel_qt](checks/test_scorebug_studio_panel_qt.log) | 11 | 0 | 7.38 | 0 |
| [test_shipped_tools_are_self_sufficient](checks/test_shipped_tools_are_self_sufficient.log) | 3 | 0 | 12.64 | 0 |
| [test_shipped_tools_posix_only](checks/test_shipped_tools_posix_only.log) | 13 | 0 | 12.03 | 0 |

The native order and down visibility suites pass. test_scorebug_gpu verifies all 52 team slots, both possessions and both aspects, including the s5 tints. test_scorebug_replication retains the palette, source pin and unverified-calibration mutation gates. Provider integrity passes all eight cases. These are offline proofs, not an in-game readability result.

Both temporary product stages, release closures and runtime closures pass:

| Product | Stage | Release closure | Runtime closure |
|---|---|---|---|
| 2k5 | PASS, 0.36s | PASS, 7.48s | PASS, 13.39s |
| apf2k8 | PASS, 0.11s | PASS, 0.42s | PASS, 13.14s |

Commands reuse the inherited runners with only their report output directory redirected. Each test runs as `PYTHONPATH=<repo> QT_QPA_PLATFORM=offscreen python3 <test file>`. Exact invocations:

```python
from pathlib import Path
from reports.b72_s6 import run_checks
run_checks.OUT = Path("reports/b72_s7/checks").resolve()
raise SystemExit(run_checks.main())
```

For closures, execute the unchanged contents of `reports/b72_s6/run_closures.py` with `__file__` set to `<repo>/reports/b72_s7/run_closures.py`; that redirects its existing OUT constant. Its temporary directories are deleted by the existing runner. No installer, disc or release artifact is produced.

```sh
python3 reports/b72_s7/analyze_vertices.py
python3 tools/scorebug_sprite/build_runtime.py --check
python3 packaging/repin.py --apply
```

The evidence recipe completes with every table/fixture assertion passing and an explicit failed luminance gate. Runtime regeneration check passes. Repin reports zero updates. No shipping file or pinned closure changed; no allowlist addition is needed for job reports. unchanged.json retains source/art/allowlist/manifest identities against b6bdf106 and the 4086 used RX bytes, 4096 reservation, ten spare bytes and 128 RW bytes.

The cave manifest is byte-identical to the base. Its previously reported stale source fingerprints are not regenerated or claimed fixed. No additional allocator/oracle regression pass is claimed for this unchanged owner.

The installed diff-gate recipe reports zero deterministic findings and zero model windows because its default excludes reports. The handoff fact-check uses the installed recipe routed through live Jev MCP; its separate receipt distinguishes actual judgments from the empty shipping-code diff gate.

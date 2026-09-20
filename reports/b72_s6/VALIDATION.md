# b72-s6 validation

All 35 required standalone test files pass: 307 cases collected, 299 executed and 8 existing skips. Every file completed below 100 seconds. Commands use plain python3, PYTHONPATH=<repo> and QT_QPA_PLATFORM=offscreen. See run_checks.py for the exact inventory and bounded subprocess invocation.

| Test file | Cases | Skips | Seconds | Result |
|---|---:|---:|---:|---|
| [test_apf_scorebug_workspace_qt](checks/test_apf_scorebug_workspace_qt.log) | 11 | 0 | 1.42 | PASS |
| [test_nfl2k5_scorebug_assets](checks/test_nfl2k5_scorebug_assets.log) | 8 | 1 | 6.33 | PASS |
| [test_nfl2k5_scorebug_author](checks/test_nfl2k5_scorebug_author.log) | 12 | 0 | 6.28 | PASS |
| [test_nfl2k5_scorebug_down_visibility](checks/test_nfl2k5_scorebug_down_visibility.log) | 2 | 0 | 19.96 | PASS |
| [test_nfl2k5_scorebug_draw_order](checks/test_nfl2k5_scorebug_draw_order.log) | 5 | 0 | 9.74 | PASS |
| [test_nfl2k5_scorebug_exact](checks/test_nfl2k5_scorebug_exact.log) | 8 | 0 | 30.83 | PASS |
| [test_nfl2k5_scorebug_fonts](checks/test_nfl2k5_scorebug_fonts.log) | 10 | 5 | 4.88 | PASS |
| [test_nfl2k5_scorebug_freeze](checks/test_nfl2k5_scorebug_freeze.log) | 7 | 0 | 17.60 | PASS |
| [test_nfl2k5_scorebug_freeze_v2](checks/test_nfl2k5_scorebug_freeze_v2.log) | 7 | 0 | 33.48 | PASS |
| [test_nfl2k5_scorebug_ingame](checks/test_nfl2k5_scorebug_ingame.log) | 11 | 0 | 7.48 | PASS |
| [test_nfl2k5_scorebug_ingame_fix](checks/test_nfl2k5_scorebug_ingame_fix.log) | 9 | 0 | 54.41 | PASS |
| [test_nfl2k5_scorebug_mnf](checks/test_nfl2k5_scorebug_mnf.log) | 10 | 0 | 11.18 | PASS |
| [test_nfl2k5_scorebug_mnf_v3](checks/test_nfl2k5_scorebug_mnf_v3.log) | 7 | 0 | 20.85 | PASS |
| [test_nfl2k5_scorebug_native](checks/test_nfl2k5_scorebug_native.log) | 4 | 0 | 21.60 | PASS |
| [test_nfl2k5_scorebug_projection](checks/test_nfl2k5_scorebug_projection.log) | 14 | 0 | 25.86 | PASS |
| [test_nfl2k5_scorebug_resources](checks/test_nfl2k5_scorebug_resources.log) | 6 | 0 | 79.36 | PASS |
| [test_nfl2k5_scorebug_runtime](checks/test_nfl2k5_scorebug_runtime.log) | 12 | 0 | 12.74 | PASS |
| [test_nfl2k5_scorebug_sd](checks/test_nfl2k5_scorebug_sd.log) | 3 | 0 | 0.57 | PASS |
| [test_nfl2k5_scorebug_source_art](checks/test_nfl2k5_scorebug_source_art.log) | 13 | 2 | 2.02 | PASS |
| [test_nfl2k5_scorebug_sprite](checks/test_nfl2k5_scorebug_sprite.log) | 19 | 0 | 21.45 | PASS |
| [test_nfl2k5_scorebug_template](checks/test_nfl2k5_scorebug_template.log) | 19 | 0 | 5.02 | PASS |
| [test_nfl2k5_scorebug_template_release](checks/test_nfl2k5_scorebug_template_release.log) | 5 | 0 | 0.57 | PASS |
| [test_nfl2k5_scorebug_unified_adapter](checks/test_nfl2k5_scorebug_unified_adapter.log) | 5 | 0 | 0.16 | PASS |
| [test_nfl2k5_scorebug_v10_ingame](checks/test_nfl2k5_scorebug_v10_ingame.log) | 11 | 0 | 6.33 | PASS |
| [test_nfl2k5_scorebug_v10_projection](checks/test_nfl2k5_scorebug_v10_projection.log) | 14 | 0 | 25.45 | PASS |
| [test_nfl2k5_scorebug_versions](checks/test_nfl2k5_scorebug_versions.log) | 4 | 0 | 4.72 | PASS |
| [test_nfl2k5_scorebug_watermark](checks/test_nfl2k5_scorebug_watermark.log) | 3 | 0 | 17.04 | PASS |
| [test_provider_integrity](checks/test_provider_integrity.log) | 8 | 0 | 9.98 | PASS |
| [test_scorebug_gpu](checks/test_scorebug_gpu.log) | 9 | 0 | 9.13 | PASS |
| [test_scorebug_live](checks/test_scorebug_live.log) | 9 | 0 | 0.16 | PASS |
| [test_scorebug_replication](checks/test_scorebug_replication.log) | 12 | 0 | 0.46 | PASS |
| [test_scorebug_sprite_preview_qt](checks/test_scorebug_sprite_preview_qt.log) | 3 | 0 | 7.17 | PASS |
| [test_scorebug_studio_panel_qt](checks/test_scorebug_studio_panel_qt.log) | 11 | 0 | 7.28 | PASS |
| [test_shipped_tools_are_self_sufficient](checks/test_shipped_tools_are_self_sufficient.log) | 3 | 0 | 12.24 | PASS |
| [test_shipped_tools_posix_only](checks/test_shipped_tools_posix_only.log) | 13 | 0 | 14.25 | PASS |

The nine new trace tests cover partial windows, absent indices, upload component/index semantics, resident program rewrites, independent windows, unhandled methods, inside-draw changes, channel separation, truncated RAM and rectangular swizzling. The existing native GPU suite also checks exact independent texture decoding, captured-filter acceptance, unsupported-filter refusal and incomplete-program refusal. Native order, down visibility and all 52 team slots at both possessions and aspects pass. No all-team fixed-output claim is made because reproduction is unresolved.

Both products were staged only into disposable temporary directories for closure checks. No installer or test disc was produced.

| Product | Check | Seconds | Exit |
|---|---|---:|---:|
| 2k5 | stage | 0.36 | 0 |
| 2k5 | release closure | 7.33 | 0 |
| 2k5 | runtime closure | 12.18 | 0 |
| apf2k8 | stage | 0.11 | 0 |
| apf2k8 | release closure | 0.41 | 0 |
| apf2k8 | runtime closure | 12.19 | 0 |

The runtime rebuild check passes (build_runtime.log). Budgets remain 4086/4096 RX, 128 RW and 324832/400000 appended bytes. Runtime owner, generated code, source, layout, template, team accent data and cave manifest are byte-identical to the base (budgets.json). No allocator request or cave write changes in this job.

The read-only cave space-proof command passes with no retail mapping or manifest overlaps (space_proof.json). Its source-fingerprint check is separate: ReservationManifest.load(..., source_root=ROOT) fails first at nfl2k5_scorebug_exact.py; the stale-source set is identical to the base (manifest_freshness.log). This job does not regenerate the manifest or hide that failure. The full auxiliary allocator/oracle suites from s5 were not repeated for unchanged runtime code; their prior limitations are not promoted to fresh passes.

New live.py is declared in the release allowlist and replication pins. repin.py updated the existing xemu_model.py pins. The exact provider import closure remains 301 entries and its integrity test passes. All declarations are part of this branch; no integrator wiring is required for the diagnostic modules.

The installed Jev diff-gate recipe reports zero deterministic findings. Its 13 live MCP hunk judgments flagged two model-extension windows; manual dispositions are in JEV_REVIEW.md. Pin changes were independently verified by the recipe. The full report and raw requests/responses are retained.

The in-game reproduction gate fails. The supplied sample has zero sprite atlas draws; the earlier state plus later RAM still predicts bright label cores. No cause-specific runtime change, no new emulator session and no in-game success claim. See GPU_FINDINGS.md and NEXT_CAPTURE.md.

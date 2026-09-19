# Final offline validation

All 35 default test files pass: 312 cases, 304 executed and 8 existing skips. The slowest file takes 76.72 seconds; each subprocess has an enforced 100-second timeout. No performance-only test environment switch is used.

| Test file | Cases | Skips | Seconds | Exit |
|---|---:|---:|---:|---:|
| [test_apf_scorebug_workspace_qt](checks/test_apf_scorebug_workspace_qt.log) | 11 | 0 | 0.56 | 0 |
| [test_nfl2k5_scorebug_assets](checks/test_nfl2k5_scorebug_assets.log) | 8 | 1 | 6.27 | 0 |
| [test_nfl2k5_scorebug_author](checks/test_nfl2k5_scorebug_author.log) | 12 | 0 | 6.27 | 0 |
| [test_nfl2k5_scorebug_down_visibility](checks/test_nfl2k5_scorebug_down_visibility.log) | 4 | 0 | 14.79 | 0 |
| [test_nfl2k5_scorebug_draw_order](checks/test_nfl2k5_scorebug_draw_order.log) | 5 | 0 | 8.53 | 0 |
| [test_nfl2k5_scorebug_exact](checks/test_nfl2k5_scorebug_exact.log) | 8 | 0 | 28.26 | 0 |
| [test_nfl2k5_scorebug_fonts](checks/test_nfl2k5_scorebug_fonts.log) | 10 | 5 | 4.47 | 0 |
| [test_nfl2k5_scorebug_freeze](checks/test_nfl2k5_scorebug_freeze.log) | 7 | 0 | 16.99 | 0 |
| [test_nfl2k5_scorebug_freeze_v2](checks/test_nfl2k5_scorebug_freeze_v2.log) | 7 | 0 | 31.91 | 0 |
| [test_nfl2k5_scorebug_ingame](checks/test_nfl2k5_scorebug_ingame.log) | 11 | 0 | 7.23 | 0 |
| [test_nfl2k5_scorebug_ingame_fix](checks/test_nfl2k5_scorebug_ingame_fix.log) | 9 | 0 | 53.15 | 0 |
| [test_nfl2k5_scorebug_mnf](checks/test_nfl2k5_scorebug_mnf.log) | 10 | 0 | 11.33 | 0 |
| [test_nfl2k5_scorebug_mnf_v3](checks/test_nfl2k5_scorebug_mnf_v3.log) | 7 | 0 | 20.40 | 0 |
| [test_nfl2k5_scorebug_native](checks/test_nfl2k5_scorebug_native.log) | 4 | 0 | 20.95 | 0 |
| [test_nfl2k5_scorebug_projection](checks/test_nfl2k5_scorebug_projection.log) | 14 | 0 | 25.45 | 0 |
| [test_nfl2k5_scorebug_resources](checks/test_nfl2k5_scorebug_resources.log) | 6 | 0 | 76.72 | 0 |
| [test_nfl2k5_scorebug_runtime](checks/test_nfl2k5_scorebug_runtime.log) | 12 | 0 | 12.18 | 0 |
| [test_nfl2k5_scorebug_sd](checks/test_nfl2k5_scorebug_sd.log) | 3 | 0 | 0.57 | 0 |
| [test_nfl2k5_scorebug_source_art](checks/test_nfl2k5_scorebug_source_art.log) | 13 | 2 | 1.92 | 0 |
| [test_nfl2k5_scorebug_sprite](checks/test_nfl2k5_scorebug_sprite.log) | 22 | 0 | 21.95 | 0 |
| [test_nfl2k5_scorebug_template](checks/test_nfl2k5_scorebug_template.log) | 19 | 0 | 4.92 | 0 |
| [test_nfl2k5_scorebug_template_release](checks/test_nfl2k5_scorebug_template_release.log) | 5 | 0 | 0.56 | 0 |
| [test_nfl2k5_scorebug_unified_adapter](checks/test_nfl2k5_scorebug_unified_adapter.log) | 5 | 0 | 0.16 | 0 |
| [test_nfl2k5_scorebug_v10_ingame](checks/test_nfl2k5_scorebug_v10_ingame.log) | 11 | 0 | 6.17 | 0 |
| [test_nfl2k5_scorebug_v10_projection](checks/test_nfl2k5_scorebug_v10_projection.log) | 14 | 0 | 25.00 | 0 |
| [test_nfl2k5_scorebug_versions](checks/test_nfl2k5_scorebug_versions.log) | 4 | 0 | 4.52 | 0 |
| [test_nfl2k5_scorebug_watermark](checks/test_nfl2k5_scorebug_watermark.log) | 3 | 0 | 16.54 | 0 |
| [test_provider_integrity](checks/test_provider_integrity.log) | 8 | 0 | 9.58 | 0 |
| [test_scorebug_gpu](checks/test_scorebug_gpu.log) | 9 | 0 | 8.63 | 0 |
| [test_scorebug_live](checks/test_scorebug_live.log) | 9 | 0 | 0.16 | 0 |
| [test_scorebug_replication](checks/test_scorebug_replication.log) | 12 | 0 | 0.46 | 0 |
| [test_scorebug_sprite_preview_qt](checks/test_scorebug_sprite_preview_qt.log) | 3 | 0 | 7.02 | 0 |
| [test_scorebug_studio_panel_qt](checks/test_scorebug_studio_panel_qt.log) | 11 | 0 | 7.27 | 0 |
| [test_shipped_tools_are_self_sufficient](checks/test_shipped_tools_are_self_sufficient.log) | 3 | 0 | 11.43 | 0 |
| [test_shipped_tools_posix_only](checks/test_shipped_tools_posix_only.log) | 13 | 0 | 11.38 | 0 |

| Product | Closure step | Seconds | Exit |
|---|---|---:|---:|
| apf2k8 | temporary stage | 0.11 | 0 |
| apf2k8 | release audit | 0.41 | 0 |
| apf2k8 | runtime audit | 11.53 | 0 |
| 2k5 | temporary stage | 0.31 | 0 |
| 2k5 | release audit | 6.72 | 0 |
| 2k5 | runtime audit | 11.38 | 0 |

Temporary product stages were removed. These are closure checks, not published release builds. The final artwork changed only the 2K5 stage; the APF closure was already verified against its unchanged bytes.

The 31 scorebug owner composition pairs pass in both orders. owner_scan.json records RX/RW permissions, absolute write destinations, idempotence and hook ownership. This auxiliary sweep is separate from the default-file budget. The retained native sequence proof covers 675 frames per aspect, 1,350 total, across pre-snap, punt/hang-time, after-play, FLAG, FUMBLE and label recovery. submission_order.json records both native material submission orders. The default draw-order test deliberately introduces bad ordering and verifies that the native renderer cannot rescue the overdrawn label.

RX is 4086/4096 bytes with 10 spare, RW is 128 bytes, and GAMEDATA appendices are 325216 bytes at both aspects against a 400000-byte ceiling. Compared with disc q, append growth is 384 bytes. build_runtime.py --check passes. repin_verify.log records no pending source-pin updates.

The exact base owner fails the new clock regression at 599.01 seconds, where the formatter rounds to 10:00 and the short formatter returns empty. The final owner selects the complementary retail formatter. Existing invalid-pointer/range guards remain. New regression cases cover fractional rollover, 10:00, 14:54, 15:00, 60:00 and return to 9:59.

The 104 final team/aspect label raster checks all pass core luminance >=200 and contrast >=4.5:1. The independent detailed visual table has 56 PASS and 40 FAIL rows, including provenance-only rows explicitly identified as such. Thus strict fidelity and screenshot calibration remain failed/unverified. Passing tests are not an in-game witness.

The cave reservation manifest and s6/s7 reports are byte-identical to 42579f4a5. Source fingerprint freshness is intentionally not a pass: the integrator must regenerate the cave manifest for the final stack. No all-owner cave/oracle-suite pass is claimed. Existing release allowlists, requirements and provider closure counts were not expanded.

The last default run caught the renamed estimated_opacity metadata key in the old test assertion. That assertion was corrected to require the honest key and the affected 22-test file rerun successfully. checks/sprite_before_metadata_correction.log retains the failed run; checks/results.json and the table above contain the final results. Older root-level repin/sprite/evidence logs are exploratory receipts and are superseded by the explicitly final files.

The Jev gate returns flagged status with reviewed dispositions, not an unconditional clean pass. See JEV_REVIEW.md. All work is offline; the integrator builds one test disc and Noah provides the next game witness.

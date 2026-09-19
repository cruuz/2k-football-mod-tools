# b72-s3 validation

The reconstruction and rebuild gates remain FAILED. Green diagnostic checks do not make this a repaired scorebug.

| File | Result | Wall seconds | 100-second target |
| --- | --- | --- | --- |
| tests/mod_editor/test_apf_scorebug_workspace_qt.py | PASS | 1.47 | PASS |
| tests/mod_editor/test_beta61_allocator_integration.py | TIMEOUT at 420 s | 420.02 | FAIL |
| tests/mod_editor/test_nfl2k5_gameplay_levers.py | PASS | 11.38 | PASS |
| tests/mod_editor/test_nfl2k5_my_career_m3_budget.py | PASS | 4.37 | PASS |
| tests/mod_editor/test_nfl2k5_roster_arena_image.py | PASS | 14.19 | PASS |
| tests/mod_editor/test_nfl2k5_roster_storage.py | PASS | 389.82 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_assets.py | PASS | 146.41 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_author.py | PASS | 6.32 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py | PASS | 39.03 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_draw_order.py | PASS | 25.05 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_exact.py | PASS | 83.31 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_fonts.py | PASS | 7.98 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_freeze.py | PASS | 240.26 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py | PASS | 326.65 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_ingame.py | PASS | 14.59 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py | PASS | 146.08 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_mnf.py | PASS | 14.75 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py | PASS | 46.78 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_native.py | PASS | 139.92 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_projection.py | PASS | 61.71 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_resources.py | PASS | 293.61 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_runtime.py | PASS | 123.92 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_sd.py | PASS | 0.72 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_source_art.py | PASS | 2.72 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_sprite.py | PASS | 109.99 | FAIL |
| tests/mod_editor/test_nfl2k5_scorebug_template.py | PASS | 9.23 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_template_release.py | PASS | 0.97 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py | PASS | 0.27 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py | PASS | 8.54 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py | PASS | 27.2 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_versions.py | PASS | 8.13 | PASS |
| tests/mod_editor/test_nfl2k5_scorebug_watermark.py | PASS | 51.45 | PASS |
| tests/mod_editor/test_provider_integrity.py | PASS | 9.68 | PASS |
| tests/mod_editor/test_scorebug_replication.py | PASS | 0.26 | PASS |
| tests/mod_editor/test_scorebug_sprite_preview_qt.py | PASS | 21.3 | PASS |
| tests/mod_editor/test_scorebug_studio_panel_qt.py | PASS | 7.33 | PASS |
| tests/mod_editor/test_shipped_tools_are_self_sufficient.py | PASS | 11.58 | PASS |
| tests/mod_editor/test_shipped_tools_posix_only.py | PASS | 11.69 | PASS |

Completed 38 files: 37 passed; 1 failed/timed out. 10 files exceeded 100 seconds.

Standalone invocation: `PYTHONPATH=<repo> QT_QPA_PLATFORM=offscreen python3 <test-file>`. The report runner enforces the 420-second ceiling per file. All logs remain in `reports/b72_s3/checks/`.

The allocator diagnostic with a 600-second outer limit is recorded separately in `beta61_extended.log`. It cannot override the 420-second timeout result.

| Other check | Result |
| --- | --- |
| New replication regression file | 12 tests passed; see replication_test.log |
| ESPN matcher, rendered fresh | 95 pass / 0 fail / 9 impossible |
| New source pin audit | 0 pending pin updates |
| Existing generated runtime | build_runtime.py --check; see runtime_build_check.log |
| Native submission order | Plate before label at both aspects; GPU boundaries remain |
| apf2k8 closure step 0 | PASS (0.12 s) |
| apf2k8 closure step 1 | PASS (0.41 s) |
| apf2k8 closure step 2 | PASS (12.59 s) |
| 2k5 closure step 0 | PASS (0.31 s) |
| 2k5 closure step 1 | PASS (7.18 s) |
| 2k5 closure step 2 | PASS (11.98 s) |

Closure steps: 0 stages an allowlist in a temporary directory, 1 checks the release file closure, 2 imports/checks the staged runtime. The runner removes each temporary stage.

Commands:

```text
python3 reports/b72_s3/run_checks.py
python3 reports/b72_s3/run_closures.py
python3 tools/scorebug_sprite/match_espn.py --frames FRAMES --output reports/b72_s3/match
python3 tools/scorebug_sprite/native.py --output submission.json
python3 packaging/repin.py
```

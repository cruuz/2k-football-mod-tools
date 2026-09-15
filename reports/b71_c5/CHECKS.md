# C5 command ledger

All checks use `PYTHONPATH=<worktree>` and `QT_QPA_PLATFORM=offscreen`. Logs retain complete stdout/stderr. Superseded runs are included; only the final checks named in ASTRA_REPORT.md certify the delivered bytes.

| Check | Exact command | Exit | Seconds | UTC start | UTC end |
|---|---|---:|---:|---|---|
| [repin_implementation](repin_implementation.log) | `python3 packaging/repin.py --apply` | 0 | 20.74 | 2026-09-15T21:04:49.163183+00:00 | 2026-09-15T21:05:09.902773+00:00 |
| [rebuild_pins](rebuild_pins.log) | `python3 -m mod_editor.core.nfl2k5_modern_color pins 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --write --workers 8` | 0 | 273.681 | 2026-09-15T21:04:50.309440+00:00 | 2026-09-15T21:09:23.990846+00:00 |
| [builder_source](builder_source.log) | `python3 reports/b71_c5/check_builder_source.py` | 0 | 0.038 | 2026-09-15T21:06:22.594604+00:00 | 2026-09-15T21:06:22.632164+00:00 |
| [registry_initial](registry_initial.log) | `python3 -m mod_editor.capabilities.validate_registry` | 1 | 0.166 | 2026-09-15T21:06:45.243405+00:00 | 2026-09-15T21:06:45.409667+00:00 |
| [evidence_hydration](evidence_hydration.log) | `python3 reports/b71_c5/hydrate_evidence.py` | 0 | 0.054 | 2026-09-15T21:09:01.648434+00:00 | 2026-09-15T21:09:01.702597+00:00 |
| [colour_gui](colour_gui.log) | `python3 tests/mod_editor/test_colour_lighting_qt.py` | 0 | 3.11 | 2026-09-15T21:09:25.019900+00:00 | 2026-09-15T21:09:28.130375+00:00 |
| [registry_strict](registry_strict.log) | `python3 -m mod_editor.capabilities.validate_registry` | 0 | 0.157 | 2026-09-15T21:09:25.034034+00:00 | 2026-09-15T21:09:25.190911+00:00 |
| [decoder_readback](decoder_readback.log) | `python3 reports/b71_c5/prove_sidelines.py --all` | 1 | 317.324 | 2026-09-15T21:09:42.237614+00:00 | 2026-09-15T21:14:59.562012+00:00 |
| [colour_controls](colour_controls.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 1 | 31.842 | 2026-09-15T21:09:43.418265+00:00 | 2026-09-15T21:10:15.260616+00:00 |
| [build_panel](build_panel.log) | `python3 tests/mod_editor/test_build_panel_qt.py` | 0 | 3.223 | 2026-09-15T21:09:43.430325+00:00 | 2026-09-15T21:09:46.653498+00:00 |
| [colour_legacy](colour_legacy.log) | `python3 tests/mod_editor/test_nfl2k5_modern_color.py` | 0 | 7.207 | 2026-09-15T21:09:43.434410+00:00 | 2026-09-15T21:09:50.641361+00:00 |
| [all_default_pins](all_default_pins.log) | `python3 tools/verify_colour_lighting_pins.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --workers 4` | 0 | 551.844 | 2026-09-15T21:09:43.445039+00:00 | 2026-09-15T21:18:55.289063+00:00 |
| [repin_recipe](repin_recipe.log) | `python3 packaging/repin.py --apply` | 0 | 30.788 | 2026-09-15T21:10:59.941345+00:00 | 2026-09-15T21:11:30.729824+00:00 |
| [repin_rounding](repin_rounding.log) | `python3 packaging/repin.py --apply` | 0 | 33.156 | 2026-09-15T21:11:54.656660+00:00 | 2026-09-15T21:12:27.812849+00:00 |
| [rebuild_pins_final](rebuild_pins_final.log) | `python3 -m mod_editor.core.nfl2k5_modern_color pins 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --write --workers 8` | 0 | 332.184 | 2026-09-15T21:11:56.421182+00:00 | 2026-09-15T21:17:28.604761+00:00 |
| [colour_gui_final](colour_gui_final.log) | `python3 tests/mod_editor/test_colour_lighting_qt.py` | 0 | 3.075 | 2026-09-15T21:12:43.260016+00:00 | 2026-09-15T21:12:46.334792+00:00 |
| [build_settings](build_settings.log) | `python3 tests/mod_editor/test_discord_bugs_1.py` | 0 | 2.241 | 2026-09-15T21:12:44.394122+00:00 | 2026-09-15T21:12:46.635173+00:00 |
| [mod_build](mod_build.log) | `python3 tests/mod_editor/test_mod_build.py` | 0 | 2.915 | 2026-09-15T21:12:45.579024+00:00 | 2026-09-15T21:12:48.494318+00:00 |
| [registry_projected](registry_projected.log) | `python3 -m mod_editor.capabilities.validate_registry --registry .scratch/b71_c5_registry.json` | 0 | 0.244 | 2026-09-15T21:14:57.486439+00:00 | 2026-09-15T21:14:57.730166+00:00 |
| [repin_snow_scope](repin_snow_scope.log) | `python3 packaging/repin.py --apply` | 0 | 25.418 | 2026-09-15T21:16:44.296359+00:00 | 2026-09-15T21:17:09.714740+00:00 |
| [preflight_model](preflight_model.log) | `python3 reports/b71_c5/preflight_model.py` | 1 | 138.288 | 2026-09-15T21:17:19.259911+00:00 | 2026-09-15T21:19:37.547645+00:00 |
| [repin_checkpoint](repin_checkpoint.log) | `python3 packaging/repin.py --apply` | 0 | 22.241 | 2026-09-15T21:18:07.306156+00:00 | 2026-09-15T21:18:29.547111+00:00 |
| [colour_controls_final](colour_controls_final.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 0 | 31.029 | 2026-09-15T21:19:07.535415+00:00 | 2026-09-15T21:19:38.564279+00:00 |
| [colour_legacy_final](colour_legacy_final.log) | `python3 tests/mod_editor/test_nfl2k5_modern_color.py` | 0 | 6.983 | 2026-09-15T21:19:08.673828+00:00 | 2026-09-15T21:19:15.657154+00:00 |
| [providers](providers.log) | `python3 tests/mod_editor/test_providers.py` | 0 | 3.749 | 2026-09-15T21:19:09.845197+00:00 | 2026-09-15T21:19:13.594346+00:00 |
| [scope_audit_initial](scope_audit_initial.log) | `python3 reports/b71_c5/audit_delivery.py` | 0 | 0.196 | 2026-09-15T21:20:18.587283+00:00 | 2026-09-15T21:20:18.782945+00:00 |
| [preflight_model_final](preflight_model_final.log) | `python3 reports/b71_c5/preflight_model.py` | 1 | 66.387 | 2026-09-15T21:21:56.215558+00:00 | 2026-09-15T21:23:02.602916+00:00 |
| [repin_model_margin](repin_model_margin.log) | `python3 packaging/repin.py --apply` | 0 | 23.466 | 2026-09-15T21:21:57.360841+00:00 | 2026-09-15T21:22:20.827324+00:00 |
| [preflight_complete](preflight_complete.log) | `python3 reports/b71_c5/preflight_model.py` | 0 | 71.647 | 2026-09-15T21:23:46.296705+00:00 | 2026-09-15T21:24:57.943813+00:00 |
| [rebuild_pins_release](rebuild_pins_release.log) | `python3 -m mod_editor.core.nfl2k5_modern_color pins 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --write --workers 8` | 0 | 321.885 | 2026-09-15T21:23:47.441309+00:00 | 2026-09-15T21:29:09.326785+00:00 |
| [preflight_all_grass](preflight_all_grass.log) | `python3 reports/b71_c5/preflight_model.py` | 1 | 78.677 | 2026-09-15T21:25:03.548681+00:00 | 2026-09-15T21:26:22.225391+00:00 |
| [repin_all_grass](repin_all_grass.log) | `python3 packaging/repin.py --apply` | 0 | 26.423 | 2026-09-15T21:25:04.715314+00:00 | 2026-09-15T21:25:31.137938+00:00 |
| [repin_scope_text](repin_scope_text.log) | `python3 packaging/repin.py --apply` | 0 | 28.047 | 2026-09-15T21:26:02.229444+00:00 | 2026-09-15T21:26:30.276744+00:00 |
| [phase1_packaging](phase1_packaging.log) | `python3 tests/mod_editor/test_phase1_packaging.py` | 0 | 3.313 | 2026-09-15T21:26:03.367142+00:00 | 2026-09-15T21:26:06.680052+00:00 |
| [colour_gui_release](colour_gui_release.log) | `python3 tests/mod_editor/test_colour_lighting_qt.py` | 0 | 3.109 | 2026-09-15T21:26:04.536066+00:00 | 2026-09-15T21:26:07.645502+00:00 |
| [preflight_full_targets](preflight_full_targets.log) | `python3 reports/b71_c5/preflight_model.py` | 0 | 73.662 | 2026-09-15T21:27:28.350202+00:00 | 2026-09-15T21:28:42.012110+00:00 |
| [repin_full_targets](repin_full_targets.log) | `python3 packaging/repin.py --apply` | 0 | 24.48 | 2026-09-15T21:27:29.522463+00:00 | 2026-09-15T21:27:54.002569+00:00 |
| [final_decoder_and_pins](final_decoder_and_pins.log) | `python3 reports/b71_c5/rebuild_and_prove.py` | 0 | 911.297 | 2026-09-15T21:29:17.237324+00:00 | 2026-09-15T21:44:28.533935+00:00 |
| [registry_final](registry_final.log) | `python3 -m mod_editor.capabilities.validate_registry` | 0 | 0.147 | 2026-09-15T21:29:18.411082+00:00 | 2026-09-15T21:29:18.558191+00:00 |
| [builder_source_final](builder_source_final.log) | `python3 reports/b71_c5/check_builder_source.py` | 0 | 0.032 | 2026-09-15T21:29:18.585849+00:00 | 2026-09-15T21:29:18.618331+00:00 |
| [repin_final](repin_final.log) | `python3 packaging/repin.py --apply` | 0 | 21.2 | 2026-09-15T21:35:02.737464+00:00 | 2026-09-15T21:35:23.937658+00:00 |
| [colour_controls_release](colour_controls_release.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 0 | 31.714 | 2026-09-15T21:35:03.890376+00:00 | 2026-09-15T21:35:35.604053+00:00 |
| [colour_legacy_release](colour_legacy_release.log) | `python3 tests/mod_editor/test_nfl2k5_modern_color.py` | 0 | 7.051 | 2026-09-15T21:35:03.911908+00:00 | 2026-09-15T21:35:10.962932+00:00 |
| [all_default_pins_final](all_default_pins_final.log) | `python3 tools/verify_colour_lighting_pins.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --workers 8` | 0 | 290.928 | 2026-09-15T21:35:03.916005+00:00 | 2026-09-15T21:39:54.844191+00:00 |
| [scope_audit](scope_audit.log) | `python3 reports/b71_c5/audit_delivery.py` | 0 | 0.186 | 2026-09-15T21:35:03.928755+00:00 | 2026-09-15T21:35:04.114291+00:00 |
| [provider_integrity](provider_integrity.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 0 | 10.048 | 2026-09-15T21:35:48.890408+00:00 | 2026-09-15T21:35:58.938725+00:00 |
| [repin_before_implementation](repin_before_implementation.log) | `python3 packaging/repin.py --apply` | 0 | 12.163 | 2026-09-15T21:36:12.761788+00:00 | 2026-09-15T21:36:24.925003+00:00 |
| [swatches](swatches.log) | `python3 reports/b71_c5/render_swatches.py` | 0 | 1.366 | 2026-09-15T21:44:42.413091+00:00 | 2026-09-15T21:44:43.778813+00:00 |
| [repin_handoff](repin_handoff.log) | `python3 packaging/repin.py --apply` | 0 | 9.942 | 2026-09-15T21:45:40.232667+00:00 | 2026-09-15T21:45:50.174382+00:00 |

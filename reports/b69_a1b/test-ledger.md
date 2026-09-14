# Standalone test ledger

Environment for every isolated run: `PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONHASHSEED=0`.
Each link retains exact stdout/stderr. JSON retains every attempt, source hashes, log hashes, projection selection and source-stability checks. Earlier failures are not discarded. The newest completed attempt is shown below.

| Test file | Outcome | Exact unittest result | Log |
| --- | --- | --- | --- |
| `test_2k5_audio_operation_integration.py` | environment failure; see exact traceback | Ran 17 tests in 2.607s; FAILED (errors=13) | [baseline](baseline/test_2k5_audio_operation_integration.log) |
| `test_2k5_build_is_explainable.py` | pass | Ran 16 tests in 0.018s; OK | [climate-integer](climate-integer/test_2k5_build_is_explainable.log) |
| `test_2k5_check_my_images.py` | environment failure; see exact traceback | Ran 21 tests in 1.240s; FAILED (errors=6, skipped=5) | [baseline](baseline/test_2k5_check_my_images.log) |
| `test_2k5_import_offers_resize.py` | environment failure; see exact traceback | Ran 11 tests in 1.697s; FAILED (errors=5) | [baseline](baseline/test_2k5_import_offers_resize.log) |
| `test_2k5_uniform_equipment_export.py` | environment failure; see exact traceback | Ran 13 tests in 0.888s; FAILED (errors=6, skipped=2) | [baseline](baseline/test_2k5_uniform_equipment_export.log) |
| `test_apf_digital_font.py` | pass | Ran 14 tests in 0.268s; OK | [final-stability](final-stability/test_apf_digital_font.log) |
| `test_apf_studio_installer.py` | environment failure; see exact traceback | Ran 16 tests in 0.127s; FAILED (errors=3) | [baseline](baseline/test_apf_studio_installer.log) |
| `test_b661_kit_build.py` | pass | Ran 2 tests in 2.390s; OK | [baseline](baseline/test_b661_kit_build.log) |
| `test_b661_workspace_qt.py` | pass | Ran 7 tests in 3.023s; OK | [baseline](baseline/test_b661_workspace_qt.log) |
| `test_b66_coach_wiring.py` | pass | Ran 5 tests in 0.857s; OK (skipped=2) | [final-stability](final-stability/test_b66_coach_wiring.log) |
| `test_b68_a1_audit.py` | pass | Ran 10 tests in 7.749s; OK | [final-stability](final-stability/test_b68_a1_audit.log) |
| `test_b68_t1_ui.py` | pass | Ran 2 tests in 0.680s; OK | [baseline](baseline/test_b68_t1_ui.log) |
| `test_b69_a1b_game_audit.py` | pass | Ran 4 tests in 1.830s; OK | [final-contract-tests](final-contract-tests/test_b69_a1b_game_audit.log) |
| `test_b69_a2_wiring.py` | pass | Ran 4 tests in 0.125s; OK | [baseline](baseline/test_b69_a2_wiring.log) |
| `test_b69_a2b_game_wiring.py` | pass | Ran 8 tests in 92.350s; OK | [climate-final](climate-final/test_b69_a2b_game_wiring.log) |
| `test_b69_j1_wiring.py` | pass | Ran 7 tests in 5.272s; OK | [baseline](baseline/test_b69_j1_wiring.log) |
| `test_beta61_allocator_integration.py` | pass | Ran 7 tests in 437.988s; OK | [allocator-fixes](allocator-fixes/test_beta61_allocator_integration.log) |
| `test_beta61_integration.py` | pass | Ran 5 tests in 10.068s; OK | [baseline](baseline/test_beta61_integration.log) |
| `test_beta62_integration3_qt.py` | pass | Ran 8 tests in 1.556s; OK | [fixes-verified](fixes-verified/test_beta62_integration3_qt.log) |
| `test_beta66_d1_panels.py` | pass | Ran 4 tests in 1.521s; OK | [baseline](baseline/test_beta66_d1_panels.log) |
| `test_beta66_helmet_finish_wiring.py` | environment failure; see exact traceback | Ran 8 tests in 11.214s; FAILED (errors=1) | [final-stability](final-stability/test_beta66_helmet_finish_wiring.log) |
| `test_beta66_supersim_wiring.py` | pass | Ran 3 tests in 0.262s; OK | [baseline](baseline/test_beta66_supersim_wiring.log) |
| `test_beta69_feedback_qt.py` | pass | Ran 5 tests in 0.359s; OK | [final-stability](final-stability/test_beta69_feedback_qt.log) |
| `test_beta69_studios_offscreen.py` | pass | Ran 1 test in 8.401s; OK | [baseline](baseline/test_beta69_studios_offscreen.log) |
| `test_build_panel_qt.py` | pass | Ran 13 tests in 2.007s; OK | [fixes-verified](fixes-verified/test_build_panel_qt.log) |
| `test_capability_registry_module_commands.py` | pass | Ran 3 tests in 0.001s; OK | [baseline](baseline/test_capability_registry_module_commands.log) |
| `test_commentary_panel_qt.py` | environment failure; see exact traceback | Ran 3 tests in 0.873s; FAILED (errors=1) | [baseline](baseline/test_commentary_panel_qt.log) |
| `test_discord_bugs_1.py` | pass | Ran 17 tests in 1.012s; OK | [baseline](baseline/test_discord_bugs_1.log) |
| `test_discord_bugs_1_wiring.py` | pass | Ran 10 tests in 2.452s; OK | [final-stability](final-stability/test_discord_bugs_1_wiring.log) |
| `test_discord_bugs_2_research.py` | pass | Ran 4 tests in 0.211s; OK | [baseline](baseline/test_discord_bugs_2_research.log) |
| `test_discord_bugs_2_wiring.py` | pass | Ran 6 tests in 0.774s; OK (skipped=2) | [baseline](baseline/test_discord_bugs_2_wiring.log) |
| `test_gameplay_patches_panel_qt.py` | pass | Ran 1 test in 0.320s; OK | [fixes-verified](fixes-verified/test_gameplay_patches_panel_qt.log) |
| `test_gui_refusal_wording.py` | pass | Ran 23 tests in 0.481s; OK | [baseline](baseline/test_gui_refusal_wording.log) |
| `test_keyboard_search_polish.py` | pass | Ran 4 tests in 1.239s; OK | [baseline](baseline/test_keyboard_search_polish.log) |
| `test_mod_build.py` | pass | Ran 11 tests in 1.483s; OK | [baseline](baseline/test_mod_build.log) |
| `test_mod_build_beta62_integration.py` | pass | Ran 8 tests in 193.323s; OK | [baseline](baseline/test_mod_build_beta62_integration.log) |
| `test_mod_build_beta62_integration3.py` | pass | Ran 11 tests in 160.245s; OK | [baseline](baseline/test_mod_build_beta62_integration3.log) |
| `test_mod_build_performance.py` | pass | Ran 6 tests in 6.661s; OK | [baseline](baseline/test_mod_build_performance.log) |
| `test_models_panel_qt.py` | pass | Ran 8 tests in 0.770s; OK (skipped=1) | [baseline](baseline/test_models_panel_qt.log) |
| `test_modpack_growth_acceptance.py` | pass | Ran 1 test in 0.000s; OK (skipped=1) | [baseline](baseline/test_modpack_growth_acceptance.log) |
| `test_music_all_modes_wiring.py` | pass | Ran 4 tests in 0.990s; OK | [baseline](baseline/test_music_all_modes_wiring.log) |
| `test_music_simple_qt.py` | pass | Ran 9 tests in 3.874s; OK | [baseline](baseline/test_music_simple_qt.log) |
| `test_music_simple_wiring.py` | pass | Ran 3 tests in 0.482s; OK | [baseline](baseline/test_music_simple_wiring.log) |
| `test_nfl2k3_2k4_compatibility_boundary.py` | pass | Ran 4 tests in 0.002s; OK | [final-stability](final-stability/test_nfl2k3_2k4_compatibility_boundary.log) |
| `test_nfl2k5_abilities_runtime.py` | pass | Ran 12 tests in 24.402s; OK | [baseline](baseline/test_nfl2k5_abilities_runtime.log) |
| `test_nfl2k5_abilities_v2.py` | pass | Ran 15 tests in 34.004s; OK | [supplemental](supplemental/test_nfl2k5_abilities_v2.log) |
| `test_nfl2k5_abilities_v2_manifest.py` | pass | Ran 2 tests in 351.733s; OK | [manifest-final](manifest-final/test_nfl2k5_abilities_v2_manifest.log) |
| `test_nfl2k5_accelerated_clock.py` | pass | Ran 40 tests in 38.828s; OK | [supplemental](supplemental/test_nfl2k5_accelerated_clock.log) |
| `test_nfl2k5_accelerated_clock_manifest.py` | pass | Ran 5 tests in 10.342s; OK | [manifest-suites](manifest-suites/test_nfl2k5_accelerated_clock_manifest.log) |
| `test_nfl2k5_allocator_scaleout.py` | pass | Ran 23 tests in 849.147s; OK | [allocator-fixes](allocator-fixes/test_nfl2k5_allocator_scaleout.log) |
| `test_nfl2k5_b661_transition.py` | pass | Ran 11 tests in 460.318s; OK | [baseline](baseline/test_nfl2k5_b661_transition.log) |
| `test_nfl2k5_b68_game_composition.py` | pass | Ran 3 tests in 411.890s; OK | [baseline](baseline/test_nfl2k5_b68_game_composition.log) |
| `test_nfl2k5_b69_rules.py` | pass | Ran 16 tests in 123.944s; OK | [baseline](baseline/test_nfl2k5_b69_rules.log) |
| `test_nfl2k5_b69_rules_series.py` | pass | Ran 1 test in 59.073s; OK | [baseline](baseline/test_nfl2k5_b69_rules_series.log) |
| `test_nfl2k5_boot_logo.py` | pass | Ran 7 tests in 1.838s; OK | [baseline](baseline/test_nfl2k5_boot_logo.log) |
| `test_nfl2k5_calendar_engine.py` | pass | Ran 9 tests in 12.882s; OK | [baseline](baseline/test_nfl2k5_calendar_engine.log) |
| `test_nfl2k5_camera_broadcast.py` | pass | Ran 9 tests in 31.468s; OK | [baseline](baseline/test_nfl2k5_camera_broadcast.log) |
| `test_nfl2k5_camera_far.py` | pass | Ran 16 tests in 94.869s; OK | [baseline](baseline/test_nfl2k5_camera_far.log) |
| `test_nfl2k5_cave_oracle.py` | pass | Ran 29 tests in 374.766s; OK (skipped=1) | [gates-after-climate](gates-after-climate/test_nfl2k5_cave_oracle.log) |
| `test_nfl2k5_college_check.py` | pass | Ran 17 tests in 6.998s; OK | [baseline](baseline/test_nfl2k5_college_check.log) |
| `test_nfl2k5_college_check_page_qt.py` | pass | Ran 11 tests in 1.902s; OK | [baseline](baseline/test_nfl2k5_college_check_page_qt.log) |
| `test_nfl2k5_coverage_trail.py` | pass | Ran 12 tests in 15.469s; OK | [supplemental](supplemental/test_nfl2k5_coverage_trail.log) |
| `test_nfl2k5_coverage_trail_unicorn.py` | pass | Ran 13 tests in 172.442s; OK | [supplemental](supplemental/test_nfl2k5_coverage_trail_unicorn.log) |
| `test_nfl2k5_cpu_money_downs.py` | pass | Ran 12 tests in 15.295s; OK | [supplemental](supplemental/test_nfl2k5_cpu_money_downs.log) |
| `test_nfl2k5_cpu_money_downs_manifest.py` | pass | Ran 3 tests in 4.252s; OK | [manifest-suites](manifest-suites/test_nfl2k5_cpu_money_downs_manifest.log) |
| `test_nfl2k5_cpu_money_downs_unicorn.py` | pass | Ran 8 tests in 26.003s; OK | [supplemental](supplemental/test_nfl2k5_cpu_money_downs_unicorn.log) |
| `test_nfl2k5_crib_reclaim.py` | pass | Ran 6 tests in 5.253s; OK | [baseline](baseline/test_nfl2k5_crib_reclaim.log) |
| `test_nfl2k5_deep_zone.py` | pass | Ran 10 tests in 166.975s; OK | [baseline](baseline/test_nfl2k5_deep_zone.log) |
| `test_nfl2k5_deep_zone_frames.py` | pass | Ran 12 tests in 259.190s; OK | [supplemental](supplemental/test_nfl2k5_deep_zone_frames.log) |
| `test_nfl2k5_defensive_try.py` | pass | Ran 23 tests in 52.820s; OK | [baseline](baseline/test_nfl2k5_defensive_try.log) |
| `test_nfl2k5_defensive_try_manifest.py` | pass | Ran 3 tests in 4.303s; OK | [manifest-suites](manifest-suites/test_nfl2k5_defensive_try_manifest.log) |
| `test_nfl2k5_defensive_try_stats.py` | pass | Ran 21 tests in 20.279s; OK | [supplemental](supplemental/test_nfl2k5_defensive_try_stats.log) |
| `test_nfl2k5_disc_identity.py` | pass | Ran 29 tests in 0.594s; OK | [baseline](baseline/test_nfl2k5_disc_identity.log) |
| `test_nfl2k5_equipment_import_wiring.py` | pass | Ran 6 tests in 0.665s; OK | [baseline](baseline/test_nfl2k5_equipment_import_wiring.log) |
| `test_nfl2k5_espn25_in_game.py` | pass | Ran 4 tests in 2.818s; OK (skipped=1) | [baseline](baseline/test_nfl2k5_espn25_in_game.log) |
| `test_nfl2k5_espn25_integration_qt.py` | pass | Ran 13 tests in 18.284s; OK | [footer-fixes](footer-fixes/test_nfl2k5_espn25_integration_qt.log) |
| `test_nfl2k5_franchise_2026.py` | pass | Ran 20 tests in 5.945s; OK | [ownership-importers](ownership-importers/test_nfl2k5_franchise_2026.log) |
| `test_nfl2k5_franchise_2026_runtime.py` | pass | Ran 11 tests in 64.562s; OK | [final-stability](final-stability/test_nfl2k5_franchise_2026_runtime.log) |
| `test_nfl2k5_franchise_2026_unicorn.py` | pass | Ran 10 tests in 1.001s; OK | [ownership-importers](ownership-importers/test_nfl2k5_franchise_2026_unicorn.log) |
| `test_nfl2k5_franchise_autosave.py` | pass | Ran 7 tests in 9.277s; OK | [baseline](baseline/test_nfl2k5_franchise_autosave.log) |
| `test_nfl2k5_franchise_edit_player.py` | pass | Ran 12 tests in 35.948s; OK | [footer-fixes](footer-fixes/test_nfl2k5_franchise_edit_player.log) |
| `test_nfl2k5_franchise_edit_player_unicorn.py` | pass | Ran 8 tests in 268.560s; OK | [supplemental](supplemental/test_nfl2k5_franchise_edit_player_unicorn.log) |
| `test_nfl2k5_franchise_practice.py` | pass | Ran 22 tests in 13.293s; OK | [baseline](baseline/test_nfl2k5_franchise_practice.log) |
| `test_nfl2k5_gameplay_levers.py` | pass | Ran 12 tests in 11.932s; OK | [baseline](baseline/test_nfl2k5_gameplay_levers.log) |
| `test_nfl2k5_guardian_manifest.py` | pass | Ran 1 test in 352.442s; OK | [manifest-final](manifest-final/test_nfl2k5_guardian_manifest.log) |
| `test_nfl2k5_guardian_overlay.py` | pass | Ran 6 tests in 7.276s; OK | [baseline](baseline/test_nfl2k5_guardian_overlay.log) |
| `test_nfl2k5_hires_families_retail.py` | pass | Ran 5 tests in 636.291s; OK | [supplemental](supplemental/test_nfl2k5_hires_families_retail.log) |
| `test_nfl2k5_jukebox_list.py` | pass | Ran 6 tests in 30.534s; OK | [baseline](baseline/test_nfl2k5_jukebox_list.log) |
| `test_nfl2k5_kick_laces.py` | pass | Ran 18 tests in 10.752s; OK | [baseline](baseline/test_nfl2k5_kick_laces.log) |
| `test_nfl2k5_kickoff_v2.py` | pass | Ran 12 tests in 34.235s; OK | [supplemental](supplemental/test_nfl2k5_kickoff_v2.log) |
| `test_nfl2k5_kickoff_v3.py` | pass | Ran 7 tests in 148.739s; OK | [supplemental](supplemental/test_nfl2k5_kickoff_v3.log) |
| `test_nfl2k5_momentum.py` | pass | Ran 23 tests in 27.600s; OK | [baseline](baseline/test_nfl2k5_momentum.log) |
| `test_nfl2k5_momentum_collisions.py` | pass | Ran 16 tests in 37.135s; OK | [baseline](baseline/test_nfl2k5_momentum_collisions.log) |
| `test_nfl2k5_music_fresh_rip_gui.py` | pass | Ran 1 test in 0.000s; OK (skipped=1) | [baseline](baseline/test_nfl2k5_music_fresh_rip_gui.log) |
| `test_nfl2k5_music_playlist_manifest.py` | pass | Ran 2 tests in 3.834s; OK | [manifest-suites](manifest-suites/test_nfl2k5_music_playlist_manifest.log) |
| `test_nfl2k5_my_career.py` | pass | Ran 13 tests in 20.373s; OK | [baseline](baseline/test_nfl2k5_my_career.log) |
| `test_nfl2k5_my_career_b69_wiring.py` | pass | Ran 3 tests in 0.346s; OK | [baseline](baseline/test_nfl2k5_my_career_b69_wiring.log) |
| `test_nfl2k5_my_career_completion.py` | pass | Ran 6 tests in 32.283s; OK | [baseline](baseline/test_nfl2k5_my_career_completion.log) |
| `test_nfl2k5_my_career_control.py` | pass | Ran 2 tests in 15.728s; OK | [baseline](baseline/test_nfl2k5_my_career_control.log) |
| `test_nfl2k5_my_career_cpu_choice.py` | pass | Ran 1 test in 18.577s; OK | [baseline](baseline/test_nfl2k5_my_career_cpu_choice.log) |
| `test_nfl2k5_my_career_cpu_frame.py` | pass | Ran 1 test in 57.355s; OK | [baseline](baseline/test_nfl2k5_my_career_cpu_frame.log) |
| `test_nfl2k5_my_career_cpu_injury.py` | pass | Ran 1 test in 24.193s; OK | [baseline](baseline/test_nfl2k5_my_career_cpu_injury.log) |
| `test_nfl2k5_my_career_cpu_period.py` | pass | Ran 2 tests in 36.756s; OK | [baseline](baseline/test_nfl2k5_my_career_cpu_period.log) |
| `test_nfl2k5_my_career_cpu_timeout.py` | pass | Ran 1 test in 18.426s; OK | [baseline](baseline/test_nfl2k5_my_career_cpu_timeout.log) |
| `test_nfl2k5_my_career_cpu_turnover.py` | pass | Ran 3 tests in 65.226s; OK | [baseline](baseline/test_nfl2k5_my_career_cpu_turnover.log) |
| `test_nfl2k5_my_career_creation_boundary.py` | pass | Ran 4 tests in 2.255s; OK | [baseline](baseline/test_nfl2k5_my_career_creation_boundary.log) |
| `test_nfl2k5_my_career_draft.py` | pass | Ran 6 tests in 1140.964s; OK | [baseline](baseline/test_nfl2k5_my_career_draft.log) |
| `test_nfl2k5_my_career_frontend.py` | pass | Ran 7 tests in 61.556s; OK | [baseline](baseline/test_nfl2k5_my_career_frontend.log) |
| `test_nfl2k5_my_career_generic_build.py` | pass | Ran 5 tests in 11.013s; OK (skipped=1) | [baseline](baseline/test_nfl2k5_my_career_generic_build.log) |
| `test_nfl2k5_my_career_inline.py` | pass | Ran 8 tests in 13.620s; OK | [baseline](baseline/test_nfl2k5_my_career_inline.log) |
| `test_nfl2k5_my_career_m3_budget.py` | pass | Ran 5 tests in 4.441s; OK | [baseline](baseline/test_nfl2k5_my_career_m3_budget.log) |
| `test_nfl2k5_my_career_m3_menus.py` | pass | Ran 4 tests in 39.262s; OK | [baseline](baseline/test_nfl2k5_my_career_m3_menus.log) |
| `test_nfl2k5_my_career_manifest.py` | pass | Ran 3 tests in 8.169s; OK | [manifest-suites](manifest-suites/test_nfl2k5_my_career_manifest.log) |
| `test_nfl2k5_my_career_mode4.py` | pass | Ran 8 tests in 435.181s; OK | [baseline](baseline/test_nfl2k5_my_career_mode4.log) |
| `test_nfl2k5_my_career_mode5.py` | pass | Ran 4 tests in 292.450s; OK | [baseline](baseline/test_nfl2k5_my_career_mode5.log) |
| `test_nfl2k5_my_career_mode_audit.py` | pass | Ran 6 tests in 0.061s; OK | [baseline](baseline/test_nfl2k5_my_career_mode_audit.log) |
| `test_nfl2k5_my_career_mode_routes.py` | pass | Ran 7 tests in 2.677s; OK | [baseline](baseline/test_nfl2k5_my_career_mode_routes.log) |
| `test_nfl2k5_my_career_panel.py` | pass | Ran 4 tests in 0.174s; OK | [baseline](baseline/test_nfl2k5_my_career_panel.log) |
| `test_nfl2k5_my_career_playcalling.py` | pass | Ran 3 tests in 772.901s; OK | [baseline](baseline/test_nfl2k5_my_career_playcalling.log) |
| `test_nfl2k5_my_career_played.py` | pass | Ran 4 tests in 60.375s; OK | [baseline](baseline/test_nfl2k5_my_career_played.log) |
| `test_nfl2k5_my_career_position_inputs.py` | pass | Ran 9 tests in 17.490s; OK | [baseline](baseline/test_nfl2k5_my_career_position_inputs.log) |
| `test_nfl2k5_my_career_prospects.py` | pass | Ran 5 tests in 293.993s; OK | [baseline](baseline/test_nfl2k5_my_career_prospects.log) |
| `test_nfl2k5_my_career_season.py` | pass | Ran 1 test in 182.004s; OK | [baseline](baseline/test_nfl2k5_my_career_season.log) |
| `test_nfl2k5_my_career_settings.py` | pass | Ran 10 tests in 28.539s; OK | [baseline](baseline/test_nfl2k5_my_career_settings.log) |
| `test_nfl2k5_my_career_signing.py` | pass | Ran 6 tests in 51.586s; OK | [baseline](baseline/test_nfl2k5_my_career_signing.log) |
| `test_nfl2k5_my_career_unicorn.py` | pass | Ran 18 tests in 12.565s; OK | [baseline](baseline/test_nfl2k5_my_career_unicorn.log) |
| `test_nfl2k5_my_career_upgrades.py` | pass | Ran 4 tests in 249.921s; OK | [baseline](baseline/test_nfl2k5_my_career_upgrades.log) |
| `test_nfl2k5_my_career_week.py` | pass | Ran 1 test in 328.613s; OK | [baseline](baseline/test_nfl2k5_my_career_week.log) |
| `test_nfl2k5_myplayer_hud.py` | pass | Ran 5 tests in 40.846s; OK | [baseline](baseline/test_nfl2k5_myplayer_hud.log) |
| `test_nfl2k5_owner_pairwise_composition.py` | pass | Ran 506 tests in 2712.982s; OK | [gates-after-climate](gates-after-climate/test_nfl2k5_owner_pairwise_composition.log) |
| `test_nfl2k5_paired_intent.py` | pass | Ran 5 tests in 31.210s; OK | [baseline](baseline/test_nfl2k5_paired_intent.log) |
| `test_nfl2k5_penalties.py` | pass | Ran 18 tests in 7.582s; OK | [baseline](baseline/test_nfl2k5_penalties.log) |
| `test_nfl2k5_play_intents_build.py` | pass | Ran 5 tests in 19.604s; OK (skipped=2) | [baseline](baseline/test_nfl2k5_play_intents_build.log) |
| `test_nfl2k5_playbook_pair.py` | pass | Ran 7 tests in 7.238s; OK | [baseline](baseline/test_nfl2k5_playbook_pair.log) |
| `test_nfl2k5_player_star.py` | pass | Ran 14 tests in 1.776s; OK | [baseline](baseline/test_nfl2k5_player_star.log) |
| `test_nfl2k5_player_star_draw.py` | pass | Ran 19 tests in 208.849s; OK | [baseline](baseline/test_nfl2k5_player_star_draw.log) |
| `test_nfl2k5_position_choices.py` | pass | Ran 11 tests in 12.302s; OK | [baseline](baseline/test_nfl2k5_position_choices.log) |
| `test_nfl2k5_position_row_probowl.py` | pass | Ran 7 tests in 3.890s; OK | [baseline](baseline/test_nfl2k5_position_row_probowl.log) |
| `test_nfl2k5_practice_reserves.py` | pass | Ran 9 tests in 20.831s; OK | [baseline](baseline/test_nfl2k5_practice_reserves.log) |
| `test_nfl2k5_practice_squad.py` | pass | Ran 27 tests in 23.208s; OK | [baseline](baseline/test_nfl2k5_practice_squad.log) |
| `test_nfl2k5_practice_squad_screen.py` | pass | Ran 10 tests in 441.241s; OK | [baseline](baseline/test_nfl2k5_practice_squad_screen.log) |
| `test_nfl2k5_prospect_names.py` | pass | Ran 21 tests in 10.226s; OK | [baseline](baseline/test_nfl2k5_prospect_names.log) |
| `test_nfl2k5_qb_spy_man_rush.py` | pass | Ran 14 tests in 407.971s; OK | [supplemental](supplemental/test_nfl2k5_qb_spy_man_rush.log) |
| `test_nfl2k5_qb_spy_runtime.py` | pass | Ran 13 tests in 455.261s; OK | [baseline](baseline/test_nfl2k5_qb_spy_runtime.log) |
| `test_nfl2k5_read_option_diagnostic.py` | pass | Ran 17 tests in 27.601s; OK (skipped=4) | [baseline](baseline/test_nfl2k5_read_option_diagnostic.log) |
| `test_nfl2k5_read_option_diagnostic_manifest.py` | pass | Ran 0 tests in 0.262s; OK (skipped=1) | [manifest-suites](manifest-suites/test_nfl2k5_read_option_diagnostic_manifest.log) |
| `test_nfl2k5_read_option_frames.py` | pass | Ran 10 tests in 36.929s; OK | [supplemental](supplemental/test_nfl2k5_read_option_frames.log) |
| `test_nfl2k5_read_option_runtime.py` | pass | Ran 13 tests in 48.735s; OK | [baseline](baseline/test_nfl2k5_read_option_runtime.log) |
| `test_nfl2k5_read_option_screen_hooks_compose.py` | pass | Ran 9 tests in 101.471s; OK | [supplemental](supplemental/test_nfl2k5_read_option_screen_hooks_compose.log) |
| `test_nfl2k5_roster_arena_growth.py` | pass | Ran 13 tests in 31.480s; OK | [coverage-gap-final](coverage-gap-final/test_nfl2k5_roster_arena_growth.log) |
| `test_nfl2k5_roster_arena_image.py` | pass | Ran 4 tests in 25.547s; OK | [supplemental](supplemental/test_nfl2k5_roster_arena_image.log) |
| `test_nfl2k5_roster_records.py` | pass | Ran 108 tests in 14.431s; OK (skipped=1) | [baseline](baseline/test_nfl2k5_roster_records.log) |
| `test_nfl2k5_roster_storage.py` | pass | Ran 11 tests in 409.756s; OK | [baseline](baseline/test_nfl2k5_roster_storage.log) |
| `test_nfl2k5_scorebug_exact.py` | pass | Ran 8 tests in 51.728s; OK | [baseline](baseline/test_nfl2k5_scorebug_exact.log) |
| `test_nfl2k5_scorebug_ingame.py` | pass | Ran 11 tests in 10.325s; OK | [baseline](baseline/test_nfl2k5_scorebug_ingame.log) |
| `test_nfl2k5_scorebug_runtime.py` | pass | Ran 12 tests in 100.427s; OK | [baseline](baseline/test_nfl2k5_scorebug_runtime.log) |
| `test_nfl2k5_scorebug_template.py` | pass | Ran 19 tests in 9.794s; OK | [baseline](baseline/test_nfl2k5_scorebug_template.log) |
| `test_nfl2k5_scorebug_v10_ingame.py` | pass | Ran 11 tests in 9.216s; OK | [baseline](baseline/test_nfl2k5_scorebug_v10_ingame.log) |
| `test_nfl2k5_scorebug_versions.py` | pass | Ran 4 tests in 6.662s; OK | [baseline](baseline/test_nfl2k5_scorebug_versions.log) |
| `test_nfl2k5_screen_hooks.py` | pass | Ran 10 tests in 11.558s; OK | [supplemental](supplemental/test_nfl2k5_screen_hooks.log) |
| `test_nfl2k5_screen_hooks_manifest.py` | pass | Ran 3 tests in 4.189s; OK | [manifest-suites](manifest-suites/test_nfl2k5_screen_hooks_manifest.log) |
| `test_nfl2k5_senior_bowl.py` | pass | Ran 26 tests in 4.598s; OK | [baseline](baseline/test_nfl2k5_senior_bowl.log) |
| `test_nfl2k5_seven_on_seven.py` | pass | Ran 19 tests in 3.308s; OK | [baseline](baseline/test_nfl2k5_seven_on_seven.log) |
| `test_nfl2k5_seven_on_seven_manifest.py` | pass | Ran 3 tests in 0.604s; OK | [manifest-suites](manifest-suites/test_nfl2k5_seven_on_seven_manifest.log) |
| `test_nfl2k5_seven_on_seven_v2.py` | pass | Ran 74 tests in 160.351s; OK | [baseline](baseline/test_nfl2k5_seven_on_seven_v2.log) |
| `test_nfl2k5_simulated_windows_build.py` | pass | Ran 1 test in 225.044s; OK | [baseline](baseline/test_nfl2k5_simulated_windows_build.log) |
| `test_nfl2k5_supersim.py` | pass | Ran 12 tests in 8.223s; OK | [baseline](baseline/test_nfl2k5_supersim.log) |
| `test_nfl2k5_supersim_live.py` | pass | Ran 34 tests in 2605.040s; OK | [supersim-final](supersim-final/test_nfl2k5_supersim_live.log) |
| `test_nfl2k5_team_column.py` | pass | Ran 13 tests in 5.787s; OK | [baseline](baseline/test_nfl2k5_team_column.log) |
| `test_nfl2k5_team_history.py` | pass | Ran 19 tests in 4.878s; OK | [baseline](baseline/test_nfl2k5_team_history.log) |
| `test_nfl2k5_throw_arc.py` | pass | Ran 10 tests in 3.646s; OK | [baseline](baseline/test_nfl2k5_throw_arc.log) |
| `test_nfl2k5_throw_tuning.py` | pass | Ran 45 tests in 10.737s; OK (skipped=1) | [dispatcher-final](dispatcher-final/test_nfl2k5_throw_tuning.log) |
| `test_nfl2k5_uniform_choice.py` | pass | Ran 18 tests in 8.885s; OK | [baseline](baseline/test_nfl2k5_uniform_choice.log) |
| `test_nfl2k5_weather.py` | pass | Ran 12 tests in 0.224s; OK | [baseline](baseline/test_nfl2k5_weather.log) |
| `test_nfl2k5_weather_editor.py` | pass | Ran 2 tests in 0.056s; OK | [baseline](baseline/test_nfl2k5_weather_editor.log) |
| `test_nfl2k5_weather_native.py` | pass | Ran 10 tests in 18.691s; OK | [baseline](baseline/test_nfl2k5_weather_native.log) |
| `test_nfl2k5_weekly_prep.py` | pass | Ran 11 tests in 12.980s; OK | [baseline](baseline/test_nfl2k5_weekly_prep.log) |
| `test_nfl2k5_widescreen_polish.py` | pass | Ran 13 tests in 8.138s; OK | [baseline](baseline/test_nfl2k5_widescreen_polish.log) |
| `test_nfl2k5_xbe_space.py` | pass | Ran 13 tests in 35.093s; OK (skipped=1) | [baseline](baseline/test_nfl2k5_xbe_space.log) |
| `test_nfl2k5_zone_drop.py` | pass | Ran 9 tests in 25.173s; OK | [baseline](baseline/test_nfl2k5_zone_drop.log) |
| `test_nfl_audio.py` | pass | Ran 18 tests in 0.646s; OK | [baseline](baseline/test_nfl_audio.log) |
| `test_no_capability_is_invisible.py` | environment failure; see exact traceback | Ran 2 tests in 0.013s; FAILED (errors=2) | [baseline](baseline/test_no_capability_is_invisible.log) |
| `test_number_sheet_quality_wiring.py` | pass | Ran 6 tests in 0.650s; OK (skipped=2) | [baseline](baseline/test_number_sheet_quality_wiring.log) |
| `test_pack_extent_resolver.py` | pass | Ran 6 tests in 1.082s; OK | [baseline](baseline/test_pack_extent_resolver.log) |
| `test_phase1_packaging.py` | environment failure; see exact traceback | Ran 23 tests in 0.080s; FAILED (errors=1) | [baseline](baseline/test_phase1_packaging.log) |
| `test_presentation_panel_qt.py` | environment failure; see exact traceback | Ran 2 tests in 0.526s; FAILED (errors=1) | [baseline](baseline/test_presentation_panel_qt.log) |
| `test_product_catalog.py` | pass | Ran 9 tests in 0.047s; OK | [baseline](baseline/test_product_catalog.log) |
| `test_product_inspection_panels_qt.py` | environment failure; see exact traceback | Ran 7 tests in 0.245s; FAILED (errors=1) | [baseline](baseline/test_product_inspection_panels_qt.log) |
| `test_product_shell_accessibility_qt.py` | environment failure; see exact traceback | Ran 6 tests in 1.150s; FAILED (errors=6) | [baseline](baseline/test_product_shell_accessibility_qt.log) |
| `test_project_document_workflow.py` | environment failure; see exact traceback | Ran 13 tests in 1.165s; FAILED (errors=6) | [baseline](baseline/test_project_document_workflow.log) |
| `test_provider_integrity.py` | pass | Ran 7 tests in 8.515s; OK | [baseline](baseline/test_provider_integrity.log) |
| `test_providers.py` | pass | Ran 33 tests in 3.658s; OK | [baseline](baseline/test_providers.log) |
| `test_roster_editor_panel_qt.py` | pass | Ran 50 tests in 3.704s; OK (skipped=1) | [baseline](baseline/test_roster_editor_panel_qt.log) |
| `test_roster_save_to_disc_wiring.py` | pass | Ran 6 tests in 1.529s; OK | [baseline](baseline/test_roster_save_to_disc_wiring.log) |
| `test_security_blockers_remediation.py` | pass | Ran 11 tests in 0.007s; OK | [baseline](baseline/test_security_blockers_remediation.log) |
| `test_share_panel_qt.py` | environment failure; see exact traceback | Ran 7 tests in 0.770s; FAILED (errors=1) | [baseline](baseline/test_share_panel_qt.log) |
| `test_sounds_panel_qt.py` | environment failure; see exact traceback | Ran 10 tests in 1.845s; FAILED (errors=1) | [baseline](baseline/test_sounds_panel_qt.log) |
| `test_stadium_editable_discovery.py` | pass | Ran 2 tests in 0.425s; OK (skipped=1) | [baseline](baseline/test_stadium_editable_discovery.log) |
| `test_startup_performance.py` | pass | Ran 8 tests in 1.928s; OK | [baseline](baseline/test_startup_performance.log) |
| `test_studio_inspection.py` | pass | Ran 2 tests in 0.309s; OK | [baseline](baseline/test_studio_inspection.log) |
| `test_studio_qt_models.py` | pass | Ran 0 tests in 0.000s; OK (skipped=1) | [baseline](baseline/test_studio_qt_models.log) |
| `test_studio_shell_layout_qt.py` | environment failure; see exact traceback | Ran 18 tests in 3.532s; FAILED (errors=18) | [baseline](baseline/test_studio_shell_layout_qt.log) |
| `test_team_kit_product_integration.py` | environment failure; see exact traceback | Ran 6 tests in 1.135s; FAILED (errors=7) | [baseline](baseline/test_team_kit_product_integration.log) |
| `test_teamkit_import_wiring.py` | pass | Ran 3 tests in 0.317s; OK | [baseline](baseline/test_teamkit_import_wiring.log) |
| `test_throw_tuning_panel_qt.py` | pass | Ran 13 tests in 1.578s; OK | [baseline](baseline/test_throw_tuning_panel_qt.log) |
| `test_unif_color_argb_parse.py` | pass | Ran 2 tests in 0.005s; OK | [baseline](baseline/test_unif_color_argb_parse.log) |
| `test_unif_color_control.py` | environment failure; see exact traceback | Ran 11 tests in 0.273s; FAILED (errors=3, skipped=2) | [baseline](baseline/test_unif_color_control.log) |
| `test_ux_build_plan_coverage_qt.py` | pass | Ran 7 tests in 1.446s; OK | [ux-coverage-final](ux-coverage-final/test_ux_build_plan_coverage_qt.log) |
| `test_ux_open_disc_hook_qt.py` | environment failure; see exact traceback | Ran 7 tests in 0.835s; FAILED (errors=4) | [baseline](baseline/test_ux_open_disc_hook_qt.log) |
| `test_validate_all_capabilities.py` | failure; inspect traceback | Ran 36 tests in 0.928s; FAILED (errors=1, skipped=1) | [final-contract-tests](final-contract-tests/test_validate_all_capabilities.log) |
| `test_visual_export_and_preview.py` | environment failure; see exact traceback | Ran 11 tests in 0.003s; FAILED (errors=2) | [baseline](baseline/test_visual_export_and_preview.log) |
| `test_workspace_recovery.py` | pass | Ran 7 tests in 0.033s; OK | [baseline](baseline/test_workspace_recovery.log) |
| `test_xbe_patch_cave_references.py` | pass | Ran 131 tests in 1764.508s; OK | [gates-after-climate](gates-after-climate/test_xbe_patch_cave_references.log) |
| `test_xbe_patch_memory_writes.py` | pass | Ran 119 tests in 1564.983s; OK | [gates-after-climate](gates-after-climate/test_xbe_patch_memory_writes.log) |
| `nfl2k5_allocator_stack.py` | pass | ; (no output) | [support-imports](support-imports/nfl2k5_allocator_stack.log) |
| `nfl2k5_b69_rules_native.py` | pass | ; (no output) | [support-imports](support-imports/nfl2k5_b69_rules_native.log) |
| `nfl2k5_b69_series.py` | pass | ; (no output) | [support-imports](support-imports/nfl2k5_b69_series.log) |
| `nfl2k5_depth_chart_rows_test.py` | pass | Ran 23 tests in 38.162s; OK | [legacy-importers-final](legacy-importers-final/nfl2k5_depth_chart_rows_test.log) |
| `nfl2k5_edge_rename_test.py` | pass | Ran 13 tests in 2.244s; OK | [legacy-importers-final](legacy-importers-final/nfl2k5_edge_rename_test.log) |
| `nfl2k5_scorebug_layout_test.py` | pass | Ran 15 tests in 1.182s; OK (skipped=6) | [legacy-importers-final](legacy-importers-final/nfl2k5_scorebug_layout_test.log) |
| `nfl2k5_throw_tuning_test.py` | pass | Ran 39 tests in 9.676s; OK (skipped=1) | [legacy-importers-final](legacy-importers-final/nfl2k5_throw_tuning_test.log) |

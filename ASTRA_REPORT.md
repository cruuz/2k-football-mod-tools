# b72-a2: APF72-B offline handoff

Base: `088e3f41`, APF `0.1.0-alpha.93`. Scope is exactly the five APF72-B editor blockers. Gameplay remains UNWITNESSED. No emulator, audio playback, disc image, runtime patch, version constant, or core writer changed.

## Changes and dossier citations

| Item | Reporter cite and dossier location | Original cause | Implemented path and regression |
| --- | --- | --- | --- |
| U20/U11, slow tabs | Urianus DM, 2026-09-17 4:49 PM #4, "still re-reads and reloads the entire thing after every edit"; 2026-09-15 10:52 PM, "3-20 seconds". `BETA72_APF_DOSSIER.md:22`, `:31`, `:65`, `:81`. | `session.py:2762-2773`, `:2394-2412`, `playbook_membership_qt.py:1600-1607` at base. | Source books and compiled MASTER/SPLB results are session-owned and keyed by source byte SHA-256 plus normalized staged requests. Successful compiled results alone are reused; changed requests, Undo and a new source session select a new key. `mod_editor/apf_studio/session.py:2351`, `mod_editor/apf_studio/session.py:2431`. Fine-tune, map and route panels offer optional pending edits and bulk confirmation with one Undo action. `tests/mod_editor/test_b72_a2_editor_blockers.py:378`. |
| U18, Shovel/relay | Urianus DM, 2026-09-17 4:49 PM #2, "after using a relay play once ... on the next slot". `BETA72_APF_DOSSIER.md:29`, `:66`, `:81`. | Original MASTER body at `session.py:2314-2322`, relay checks at `:2624-2642`; writer chain-set guard at `core/apf2k8_playbook_route_writer.py:396-407`. | Relay multiplicities use the same compiled staged view as validation, and a relay carries the target's currently staged route using a stable stock selector. `mod_editor/apf_studio/session.py:2666`, `mod_editor/apf_studio/session.py:2686`. Exact local H Shovel Strong/H Lead Shovel OL regression: `tests/mod_editor/test_b72_a2_editor_blockers.py:355`. The base fails the consumed-relay assertion; the fix preserves every original chain start. |
| U19, sorting | Urianus DM, 2026-09-17 4:49 PM #3, "Sorting doesn't work for any of the tables under CPU Play Calling". `BETA72_APF_DOSSIER.md:30`, `:64`, `:81`. | Shared `playcalling_editor_qt.py:60-78` had no sorting. | All nine tables enable sorting with numeric comparison and a stable original-row key. Refill disables sorting while populating complete rows, restores selection and preserves the sort indicator. Category, candidate and pending buttons resolve model rows after sorting. `mod_editor/apf_studio/playcalling_editor_qt.py:64`, `mod_editor/apf_studio/playcalling_editor_qt.py:103`, `tests/mod_editor/test_b72_a2_editor_blockers.py:67`. |
| U17, recent projects | Urianus DM, 2026-09-17 4:49 PM #1, "listed ones aren't clickable". `BETA72_APF_DOSSIER.md:28`, `:63`, `:81`. | `gui.py:20372-20376` required `source_ready`. | Recent projects stay enabled on a cold start and remember the source in private workspace metadata. Loading is source first, project second, through existing recognition and fingerprint validation. Missing sources report a next step. `mod_editor/apf_studio/gui.py:21480`, `mod_editor/apf_studio/project.py:454`, `tests/mod_editor/test_b72_a2_editor_blockers.py:141`. |
| U12, empty destination | Urianus DM, 2026-09-17 2:00 PM, "Error when building a game folder into an empty folder". `BETA72_APF_DOSSIER.md:23`, `:62`, `:81`. | GUI `gui.py:21788` only prompted for non-empty folders, but `build.py:815-820` rejected every existing folder. | Existing empty directories are valid without a replacement flag or prompt. Non-empty destinations require confirmation; the source-root guard is unchanged. Publication refuses if an unconfirmed empty target gained files during the build. `mod_editor/apf_studio/build.py:821`, `tests/mod_editor/test_b72_a2_editor_blockers.py:178`, `tests/mod_editor/test_b72_a2_editor_blockers.py:204`. |

## Timing proof

Local fixture: O-ManBlock, outer 130; retail MASTER has 586 plays. Measurements use `time.perf_counter`, five warm repetitions after first load, offscreen Qt on this Linux host. They do not describe in-game performance or native Windows/macOS timings.

| Repeated validation/query path | Base median ms | Changed median ms | Changed maximum ms |
| --- | ---: | ---: | ---: |
| Fine-tune Plays | 43.020 | 0.020 | 0.026 |
| Who lines up | 143.629 | 0.185 | 0.194 |
| Assignment Routes | 38.225 | 2.566 | 2.585 |

Actual Qt refreshes with membership, package-map and route edits staged, including processing the event queue after the first-load layout:

| Tab | Median ms | Maximum ms |
| --- | ---: | ---: |
| Assignment Routes | 0.050 | 0.081 |
| Fine-tune Plays | 3.770 | 23.235 |
| Who lines up | 1.239 | 2.313 |

All three refresh maxima are below 100 ms. The ten-edit Fine-tune panel benchmark measured 721.4 ms at the base versus 96.7 ms for pending edits plus 23.5 ms for confirmation. The output SHA-256 matches exactly: `6023eee3b6ad9d45ce6ab066603abac198d8a2a68aaf504ed64d15e30107f829`. The H7A encoder was replaced with an assertion during the edit loop. Pending-mode regressions also replace compilers with assertions, then confirm through the real writers. Full checks remain at confirmation and build.

Receipts: `reports/b72-a2/timing-before.json`, `timing-after.json`, `timing-ten-edits.json`, `tests/test_b72_a2_editor_blockers.log`, and `shovel-before.log`. No retail payload is included.

## Verification

Standalone CI-style run: **94 files, 1030 tests, 3 explicit skips, zero file failures**. Skips remain visible in each log. The existing playcalling suites pass. The focused pytest run also passed 64 tests before the standalone sweep. The sweep caught a Coverage Geometry source/defaults regression, which was fixed by retaining the source accessor and adding an explicit staged accessor. Its complete integration suite passes after the correction. Installer isolation initially hid the host's user-site Capstone; the unchanged installer tests pass with Capstone 5.0.7 available in a local test virtual environment. Initial and final receipts are retained separately.

Commands run from the worktree root:

```sh
python3 reports/b72-a2/run_tests.py
python3 reports/b72-a2/benchmark.py --baseline
python3 reports/b72-a2/benchmark.py
QT_QPA_PLATFORM=offscreen python3 reports/b72-a2/benchmark_edits.py
QT_QPA_PLATFORM=offscreen python3 reports/b72-a2/prove_shovel_baseline.py
```

Selected final reruns use `reports/b72-a2/rerun_tests.py` with `.scratch/test-venv/bin/python3` and that environment's `bin` directory first on `PATH`, so the installer subprocess uses the same installed dependencies. `final-rerun.log` lists the exact rerun files and interpreter. `repin-check.log` reports zero pin updates.

The runner invokes each file as `QT_QPA_PLATFORM=offscreen PYTHONPATH=<repo> python3 <file>`, two independent files at a time, with the timing test last and alone. `test-results.json` records each file's latest exit code and duration. `test-results-initial.json` and `tests-initial/` retain the initial sweep and superseded rerun receipts. `test-files.txt` records the exact selection, and `tests/` holds complete output. The Shovel baseline command succeeds only when the original consumed-relay assertion fails as expected.

| Test file | Tests | Exit |
| --- | ---: | ---: |
| `tests/mod_editor/test_apf2k8_playbook_route_writer.py` | 12 | 0 |
| `tests/mod_editor/test_apf_all_crest_slots.py` | 15 | 0 |
| `tests/mod_editor/test_apf_audio_annotation_facade.py` | 4 | 0 |
| `tests/mod_editor/test_apf_audio_annotations.py` | 11 | 0 |
| `tests/mod_editor/test_apf_audio_batch_gui.py` | 7 | 0 |
| `tests/mod_editor/test_apf_audio_drop_zone_gui.py` | 9 | 0 |
| `tests/mod_editor/test_apf_audio_encoder_gui.py` | 8 | 0 |
| `tests/mod_editor/test_apf_audio_import_idle_barrier.py` | 1 | 0 |
| `tests/mod_editor/test_apf_audio_pcm_product_backend.py` | 11 | 0 |
| `tests/mod_editor/test_apf_audio_replacement_pack.py` | 57 | 0 |
| `tests/mod_editor/test_apf_audio_waveform_qt.py` | 9 | 0 |
| `tests/mod_editor/test_apf_audo_product_backend.py` | 3 | 0 |
| `tests/mod_editor/test_apf_audo_project.py` | 3 | 0 |
| `tests/mod_editor/test_apf_ausb_product_backend.py` | 7 | 0 |
| `tests/mod_editor/test_apf_b69_build.py` | 1 | 0 |
| `tests/mod_editor/test_apf_b69_control_audit.py` | 1 | 0 |
| `tests/mod_editor/test_apf_b69_editor_qt.py` | 4 | 0 |
| `tests/mod_editor/test_apf_b69_launch_patches.py` | 5 | 0 |
| `tests/mod_editor/test_apf_b69_schemes.py` | 5 | 0 |
| `tests/mod_editor/test_apf_b69_wiring.py` | 2 | 0 |
| `tests/mod_editor/test_apf_b70_stock_recipes.py` | 5 | 0 |
| `tests/mod_editor/test_apf_b711_book_scope.py` | 3 | 0 |
| `tests/mod_editor/test_apf_b711_overlay_books_qt.py` | 6 | 0 |
| `tests/mod_editor/test_apf_b711_weight_preview.py` | 2 | 0 |
| `tests/mod_editor/test_apf_b71_editor_workflow.py` | 13 | 0 |
| `tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | 7 | 0 |
| `tests/mod_editor/test_apf_b71_situation_mask.py` | 6 | 0 |
| `tests/mod_editor/test_apf_b71_situation_mask_qt.py` | 2 | 0 |
| `tests/mod_editor/test_apf_b71_situations.py` | 10 | 0 |
| `tests/mod_editor/test_apf_book_identity_qt.py` | 7 | 0 |
| `tests/mod_editor/test_apf_browser_workspace_handoff.py` | 20 | 0 |
| `tests/mod_editor/test_apf_build_ausb_overlays.py` | 5 | 0 |
| `tests/mod_editor/test_apf_build_raw_span_overlays.py` | 7 | 0 |
| `tests/mod_editor/test_apf_capability_action_parity.py` | 11 | 0 |
| `tests/mod_editor/test_apf_crest_budget_import.py` | 12 | 0 |
| `tests/mod_editor/test_apf_cross_domain_audio_safety.py` | 4 | 0 |
| `tests/mod_editor/test_apf_custom_team_appearance_patch.py` | 8 | 0 |
| `tests/mod_editor/test_apf_endzone_dxt5a.py` | 10 | 0 |
| `tests/mod_editor/test_apf_field_art_gui.py` | 17 | 0 |
| `tests/mod_editor/test_apf_field_art_stock_label.py` | 13 | 0 |
| `tests/mod_editor/test_apf_field_material_project.py` | 4 | 0 |
| `tests/mod_editor/test_apf_g12_surfaces.py` | 12 | 0 |
| `tests/mod_editor/test_apf_helmet_crest_design_product.py` | 13 | 0 |
| `tests/mod_editor/test_apf_helmet_logo_placement.py` | 15 | 0 |
| `tests/mod_editor/test_apf_model_export_gui.py` | 5 | 0 |
| `tests/mod_editor/test_apf_number_texture_writer.py` | 25 | 0 |
| `tests/mod_editor/test_apf_package_map_writer.py` | 40 | 0 |
| `tests/mod_editor/test_apf_play_designer_project.py` | 5 | 0 |
| `tests/mod_editor/test_apf_playbook_route_gui.py` | 7 | 0 |
| `tests/mod_editor/test_apf_playcalling_editor_build.py` | 4 | 0 |
| `tests/mod_editor/test_apf_playcalling_editor_facade.py` | 7 | 0 |
| `tests/mod_editor/test_apf_playcalling_editor_patches.py` | 3 | 0 |
| `tests/mod_editor/test_apf_playcalling_editor_qt.py` | 13 | 0 |
| `tests/mod_editor/test_apf_player_position_product_backend.py` | 7 | 0 |
| `tests/mod_editor/test_apf_player_rating_patch.py` | 12 | 0 |
| `tests/mod_editor/test_apf_player_rating_product_backend.py` | 5 | 0 |
| `tests/mod_editor/test_apf_player_rating_sheet_import.py` | 7 | 0 |
| `tests/mod_editor/test_apf_product_findings_gui.py` | 2 | 0 |
| `tests/mod_editor/test_apf_project_document_workflow.py` | 13 | 0 |
| `tests/mod_editor/test_apf_project_streaming.py` | 6 | 0 |
| `tests/mod_editor/test_apf_ps3_speed.py` | 15 | 0 |
| `tests/mod_editor/test_apf_ps3_speed_packages.py` | 6 | 0 |
| `tests/mod_editor/test_apf_ps3_texture_bundle.py` | 28 | 0 |
| `tests/mod_editor/test_apf_roster_identity.py` | 18 | 0 |
| `tests/mod_editor/test_apf_roster_identity_gui.py` | 17 | 0 |
| `tests/mod_editor/test_apf_save_playbook_assignments_gui.py` | 8 | 0 |
| `tests/mod_editor/test_apf_save_roster_players_gui.py` | 4 | 0 |
| `tests/mod_editor/test_apf_scorebug_workspace_qt.py` | 11 | 0 |
| `tests/mod_editor/test_apf_shell_search_accessibility_qt.py` | 3 | 0 |
| `tests/mod_editor/test_apf_splb_add_multiple_formations.py` | 14 | 0 |
| `tests/mod_editor/test_apf_splb_formation_personnel.py` | 11 | 0 |
| `tests/mod_editor/test_apf_splb_tag_reassignment.py` | 86 | 0 |
| `tests/mod_editor/test_apf_splb_writer.py` | 22 | 0 |
| `tests/mod_editor/test_apf_stadium_studio_gui.py` | 2 | 0 |
| `tests/mod_editor/test_apf_studio_audio_gui.py` | 32 | 0 |
| `tests/mod_editor/test_apf_studio_core.py` | 9 | 0 |
| `tests/mod_editor/test_apf_studio_draft_logo.py` | 7 | 0 |
| `tests/mod_editor/test_apf_studio_installer.py` | 16 | 0 |
| `tests/mod_editor/test_apf_studio_safety.py` | 27 | 0 |
| `tests/mod_editor/test_apf_studio_text_edit.py` | 7 | 0 |
| `tests/mod_editor/test_apf_team_art.py` | 10 | 0 |
| `tests/mod_editor/test_apf_team_crest_selection.py` | 9 | 0 |
| `tests/mod_editor/test_apf_team_logo_gui.py` | 23 | 0 |
| `tests/mod_editor/test_apf_text_sheet_gui.py` | 3 | 0 |
| `tests/mod_editor/test_apf_textlogo_gui.py` | 5 | 0 |
| `tests/mod_editor/test_apf_textlogo_writer.py` | 8 | 0 |
| `tests/mod_editor/test_apf_theme_layout_qt.py` | 8 | 0 |
| `tests/mod_editor/test_apf_uniform_equipment_colors.py` | 7 | 0 |
| `tests/mod_editor/test_apf_uniform_inventory_gui.py` | 6 | 0 |
| `tests/mod_editor/test_apf_wave_integration.py` | 8 | 0 |
| `tests/mod_editor/test_apf_workspace_recovery.py` | 20 | 0 |
| `tests/mod_editor/test_apf_xma1_wizard_gui.py` | 17 | 0 |
| `tests/mod_editor/test_b69_a1_playcalling.py` | 2 | 0 |
| `tests/mod_editor/test_b72_a2_editor_blockers.py` | 13 | 0 |

## Boundaries and delivery

- Pending mode is optional and starts off, matching the existing CPU Play Calling workflow. Pending edits require confirmation before the main Build action. Fine-tune and route confirmation are atomic; failures retain pending edits and restore the session.
- Older recent-project records contain no project-to-source binding. They remain clickable and explain that the source must be loaded once. New saves and opens record the binding locally; project archives still contain no machine-specific source paths.
- Paths use `Path`/`os.fspath`, temporary locations use `tempfile`, and offscreen tests include paths with spaces. Native Windows/macOS execution was not performed.
- `tools/apf_h7a_optimal` is mode 0755. No helper rebuild or umask-induced mode change is shipped. No pinned core writer changed, so no repin or registry count change is required.
- The checkout's shared `.git` is read-only in this sandbox. Commits and branch `b72-a2` are assembled in `.scratch/b72-a2.git`, using read-only access to the base objects. Product edits remain in this worktree. The portable delivery is `.scratch/astra-b72-a2.bundle`; its prerequisite is `088e3f41`. No shared checkout, other worktree, or remote was changed.
- `WIRING.md` records zero new capability rows and no protected-file changes. All five fixes are offline-proved editor behavior. Gameplay remains UNWITNESSED; no in-game acceptance claim is made.

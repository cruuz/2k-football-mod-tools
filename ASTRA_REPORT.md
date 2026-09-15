# Beta 71 C3: Colour & lighting controls

## Delivery

- Branch: `astra/b71-c3-lighting-controls`, based on `fable/b71-color2` at `a7ada82e3d55b0f6c207770fc5da838886feff9b` (v2.1).
- Private Git directory: `.scratch/astra-c3.git`. The linked worktree Git directory was not modified. Commits use explicit paths; no push.
- Bundle: `.scratch/astra-b71-c3.bundle` (incremental, requires the v2.1 base).
- Runtime controls, writer parameters, project persistence, publication of receipts, registry evidence and RC96 changelog are wired directly. No deferred wiring.
- No emulator, display server or audio was opened. Qt ran with `QT_QPA_PLATFORM=offscreen`. No scorebug module was edited. No disc or pack copy was made.

## Result and evidence

All requested checks pass. The detached XBE gates passed 119 memory-write tests and 131 cave-reference tests. Full process durations were 1629.920 s and 1822.416 s.

**PROVED:** 55 sliders, 55 per-slider switches, 13 group switches, two surface links, stadium-class and condition selectors, and Broadcast (default) / Retail reset buttons. Off preserves the authored value but uses that lever's retail value. Master enable remains Off in all three presets; presets leave the custom project recipe intact. Both reset buttons preserve the master enable choice.

**PROVED:** all 477 complete default bundle pins and seven light-table pins reproduce v2.1 exactly (`tools/verify_colour_lighting_pins.py`, 390.999 seconds). The shipped pins JSON is unchanged. Later receipt bookkeeping and displayed-default normalization retain the exact writer coefficients and do not change pixel, table or wrapper bytes. The original colour suite also verifies a decoded Arrowhead bundle against its v2.1 pin.

**PROVED:** the calibrated model reproduces the captured beta-70 night colour (51,61,32); the report's v2.1 map (181,216,102) predicts night (102,122,52) and day (83,99,47). Every control row shows the current predicted turf and broadcast target. Three labelled numeric representatives cover outdoor colour maps, dome colour maps and material-only turf. The Indianapolis / Detroit broadcast targets come from the existing Week 1 table; the retail colour-map mean and material word were decoded read-only from s11dd / s09dd in this session.

**PROVED:** custom palette / tint / normal and seven-rig parameters use `mod_editor/core/nfl2k5_modern_color.py`. Custom Arrowhead refits preserve all 32-byte wrappers, fixed spans, decoded sizes and bump mip bytes. Key directions, light counts and shadows remain retail; only the original colour/intensity floats and section digest change in the executable.

**PROVED:** normalized settings survive BuildPlan conversion, actual project archive save/load, restoration into a new offscreen BuildPanel, preset changes, per-lever Off/On and link/unlink. No project schema or preset toggle is repurposed.

**PROVED:** custom status is `applied (custom)` with a matching `<disc>.colour-lighting.json` receipt. Receipts contain canonical settings and their SHA-256, every bundle's source/result hashes, fixed-site hashes and unfit reasons. The normal build receipt includes the bundle pins. Read-back validates archive identity, fixed-site scope and entire bundle hashes. Replay performs no archive writes and persists the replay counts; a foreign byte or shifted receipt site is refused. The receipt is published alongside the finished disc, and a later retail build removes a stale destination sidecar.

**PROVED:** strict registry validation passes with 174 rows; the existing colour row is expanded, no row is added. Provider closure is pinned at 286 modules (the existing colour owner is newly reached by saved-settings validation), and its existing data pins JSON is also pinned/staged. An isolated provider process loads the defaults using only its staged source and data dependencies.

**UNWITNESSED:** custom settings in an actual game, all extrapolated class/condition predictions, clipping of white uniforms/skin at extreme gain, mowing-band appearance and far-field shimmer. The approved v2.1 baseline is retained; this session makes no new in-game appearance claim.

## Model and reset limits

The swatch uses `predicted_on_screen`: map × (ambient colour × intensity + sum of light colour × intensity) × SCREEN_FACTOR. It predicts the turf mean only. It does not simulate divot coverage, relief, tints, edge falloff or stripe contrast; those sliders intentionally do not move the mean swatch. Only outdoor day/night are calibrated. Dome/material turf, afternoon, rain, snow and alternate rigs are explicitly labelled extrapolations. Preview class/condition are saved but excluded from the writer settings digest.

Night and dome share the retail `night_indoor` table. They cannot be independently adjusted without changing the selector, which this job does not do. Map contrast acts on existing green value deviations around the used-green mean; it can adjust bands already in the colour map and cannot synthesize mowing stripes. Its GUI row is unavailable for material-only turf.

Palette grading is lossy. Broadcast and Retail reset the project controls; to change or reset a grade already baked into a disc, select the original retail source. Preflight names that cause and next step before copying. This replaces the earlier behaviour where Off restored only the rig while keeping graded grass. The exact same already-applied recipe may replay with its matching receipt. A custom disc without that sidecar is not recognized as custom.

A refit that cannot preserve its retail wrapper/scratch allowance keeps the original span and names `unfit` in its receipt. The predictive model is not a promise that an extreme custom scene will fit. No new XBE writer, hook, cave, runtime state or write address was added.

## Every control

All writer functions below are in `mod_editor/core/nfl2k5_modern_color.py`. The complete parameter contract is also in `docs/modern_color/CONTROLS.md`. Range endpoints are inclusive. Each row has an individual toggle; group toggles default On under the stored Broadcast recipe, while the Build master defaults Off.

| Lever / control key | v2.1 default | Range (step) | Off value | Existing writer path |
|---|---:|---|---:|---|
| `turf.hue_target` (Broadcast hue (degrees)) | 72 | 45–150 (1) | 72 | regrade_palette / regrade_colour_word → modern_field_scene |
| `turf.hue_pull` (Hue pull) | 0.5 | 0–1 (0.01) | 0 | regrade_palette / regrade_colour_word → modern_field_scene |
| `turf.saturation` (Saturation) | 1.12 | 0–2 (0.01) | 1 | regrade_palette / regrade_colour_word → modern_field_scene |
| `turf.value_lift` (Brightness curve) | 2.8 | 0.25–5 (0.01) | 1 | regrade_palette / regrade_colour_word → modern_field_scene |
| `endzones.hue_target` (Broadcast hue (degrees)) | 72 | 45–150 (1) | 72 | regrade_palette / regrade_colour_word → modern_field_scene |
| `endzones.hue_pull` (Hue pull) | 0.5 | 0–1 (0.01) | 0 | regrade_palette / regrade_colour_word → modern_field_scene |
| `endzones.saturation` (Saturation) | 1.12 | 0–2 (0.01) | 1 | regrade_palette / regrade_colour_word → modern_field_scene |
| `endzones.value_lift` (Brightness curve) | 2.8 | 0.25–5 (0.01) | 1 | regrade_palette / regrade_colour_word → modern_field_scene |
| `outside.hue_target` (Broadcast hue (degrees)) | 72 | 45–150 (1) | 72 | regrade_palette / regrade_colour_word → modern_field_scene |
| `outside.hue_pull` (Hue pull) | 0.5 | 0–1 (0.01) | 0 | regrade_palette / regrade_colour_word → modern_field_scene |
| `outside.saturation` (Saturation) | 1.12 | 0–2 (0.01) | 1 | regrade_palette / regrade_colour_word → modern_field_scene |
| `outside.value_lift` (Brightness curve) | 2.8 | 0.25–5 (0.01) | 1 | regrade_palette / regrade_colour_word → modern_field_scene |
| `turf.map_contrast` (Map contrast / mowing stripes) | 1 | 0–2 (0.01) | 1 | regrade_palette / regrade_colour_word → modern_field_scene |
| `outside.match` (Match field brightness) | 1 | 0–1 (0.01) | 0 | modern_field_scene (used-green ratio / vertex falloff) |
| `outside.falloff` (Edge shade strength) | 0.45 | 0–1 (0.01) | 1 | modern_field_scene (used-green ratio / vertex falloff) |
| `divots.contrast` (Blotch / wear contrast) | 0.3 | 0–1 (0.01) | 1 | regrade_palette → modern_divots_span (DIVOTS_ALPHA) |
| `normal.flatten` (Bump flatten amount) | 0.68 | 0–1 (0.01) | 0 | flatten_normal_palette → modern_normal_span |
| `tints.day` (Day tint correction) | 1 | 0–2 (0.01) | 0 | corrected_tint / corrected_tint_word → modern_field_scene / modern_bundle |
| `tints.afternoon` (Afternoon tint correction) | 1 | 0–2 (0.01) | 0 | corrected_tint / corrected_tint_word → modern_field_scene / modern_bundle |
| `tints.night` (Night tint correction) | 1 | 0–2 (0.01) | 0 | corrected_tint / corrected_tint_word → modern_field_scene / modern_bundle |
| `rig_day.gain` (Overall gain) | 1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_day.balance` (White balance (retail to broadcast)) | 1 | 0–1 (0.01) | 0 | modern_table → apply (existing .rdata tables) |
| `rig_day.ambient` (Ambient strength) | 0.58 | 0–2 (0.01) | 0.285 | modern_table → apply (existing .rdata tables) |
| `rig_day.key` (Key light strength) | 1.2 | 0–2 (0.01) | 1.2 | modern_table → apply (existing .rdata tables) |
| `rig_day.fill` (Fill light strength) | 0.48 | 0–2 (0.01) | 0.2 | modern_table → apply (existing .rdata tables) |
| `rig_night_indoor.gain` (Overall gain) | 1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_night_indoor.balance` (White balance (retail to broadcast)) | 1 | 0–1 (0.01) | 0 | modern_table → apply (existing .rdata tables) |
| `rig_night_indoor.ambient` (Ambient strength) | 0.5 | 0–2 (0.01) | 0.31 | modern_table → apply (existing .rdata tables) |
| `rig_night_indoor.key` (Key light strength) | 0.86 | 0–2 (0.01) | 0.672 | modern_table → apply (existing .rdata tables) |
| `rig_night_indoor.fill` (Fill light strength) | 0.86 | 0–2 (0.01) | 0.672 | modern_table → apply (existing .rdata tables) |
| `rig_alt_day.gain` (Overall gain) | 1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_alt_day.balance` (White balance (retail to broadcast)) | 1 | 0–1 (0.01) | 0 | modern_table → apply (existing .rdata tables) |
| `rig_alt_day.ambient` (Ambient strength) | 0.45 | 0–2 (0.01) | 0.39 | modern_table → apply (existing .rdata tables) |
| `rig_alt_day.key` (Key light strength) | 1.1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_alt_day.fill` (Fill light strength) | 0.4 | 0–2 (0.01) | 0.3675 | modern_table → apply (existing .rdata tables) |
| `rig_alt_dynamic.gain` (Overall gain) | 1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_alt_dynamic.balance` (White balance (retail to broadcast)) | 1 | 0–1 (0.01) | 0 | modern_table → apply (existing .rdata tables) |
| `rig_alt_dynamic.ambient` (Ambient strength) | 0.42 | 0–2 (0.01) | 0.318 | modern_table → apply (existing .rdata tables) |
| `rig_alt_dynamic.key` (Key light strength) | 1.1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_alt_dynamic.fill` (Fill light strength) | 0.4 | 0–2 (0.01) | 0.3675 | modern_table → apply (existing .rdata tables) |
| `rig_rain.gain` (Overall gain) | 1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_rain.balance` (White balance (retail to broadcast)) | 1 | 0–1 (0.01) | 0 | modern_table → apply (existing .rdata tables) |
| `rig_rain.ambient` (Ambient strength) | 0.46 | 0–2 (0.01) | 0.348 | modern_table → apply (existing .rdata tables) |
| `rig_rain.key` (Key light strength) | 0.7 | 0–2 (0.01) | 0.502 | modern_table → apply (existing .rdata tables) |
| `rig_rain.fill` (Fill light strength) | 0.7 | 0–2 (0.01) | 0.502 | modern_table → apply (existing .rdata tables) |
| `rig_snow.gain` (Overall gain) | 1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_snow.balance` (White balance (retail to broadcast)) | 1 | 0–1 (0.01) | 0 | modern_table → apply (existing .rdata tables) |
| `rig_snow.ambient` (Ambient strength) | 0.5 | 0–2 (0.01) | 0.4 | modern_table → apply (existing .rdata tables) |
| `rig_snow.key` (Key light strength) | 0.62 | 0–2 (0.01) | 0.342 | modern_table → apply (existing .rdata tables) |
| `rig_snow.fill` (Fill light strength) | 0.62 | 0–2 (0.01) | 0.342 | modern_table → apply (existing .rdata tables) |
| `rig_afternoon.gain` (Overall gain) | 1 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_afternoon.balance` (White balance (retail to broadcast)) | 1 | 0–1 (0.01) | 0 | modern_table → apply (existing .rdata tables) |
| `rig_afternoon.ambient` (Ambient strength) | 0.45 | 0–2 (0.01) | 0.27 | modern_table → apply (existing .rdata tables) |
| `rig_afternoon.key` (Key light strength) | 1.2 | 0–2 (0.01) | 1 | modern_table → apply (existing .rdata tables) |
| `rig_afternoon.fill` (Fill light strength) | 0.26 | 0–2 (0.01) | 0.15 | modern_table → apply (existing .rdata tables) |

Group switch keys: `turf`, `endzones`, `outside`, `divots`, `normal`, `tints`, `rig_day`, `rig_afternoon`, `rig_night_indoor`, `rig_rain`, `rig_snow`, `rig_alt_day`, `rig_alt_dynamic`.

Links: `endzones=True`, `outside=True` by default; both are booleans. When linked, hue target/pull, saturation and brightness come from turf. Unlinked values stay saved. Outside `match` and `falloff` remain separately adjustable.

Bump flatten 0.68 leaves the existing NORMAL_FLATTEN=0.32 amplitude. Tint correction 1 keeps the existing v2.1 targets: afternoon FFFFEECD→FFFFF5E6, night FFF2FFFF→FFFFFFFF, and day vertex (255,255,229)→(255,255,240). Gain multiplies ambient/key/fill intensity. White balance 0 keeps the retail warm/cool colours; 1 uses the v2.1 broadcast rig colours.

## Files and integration scope

- `mod_editor/core/nfl2k5_modern_color.py`: settings contract, calibrated preview, parameters, fixed-span refits, custom receipts and verification; original owner only.
- `mod_editor/gui/colour_lighting_qt.py` and `build_panel_qt.py`: editor controls beside the existing checkbox, live swatches, BuildPlan and applied/custom state.
- `mod_editor/gui/gameplay_project_ui.py`, `mod_editor/core/nfl2k5_build_settings.py`: project capture, restoration and dirty notifications.
- `mod_editor/core/mod_build.py`: preflight and parameter routing; carries receipts through project staging and publishes them beside the final disc.
- `mod_editor/core/providers.py`, `packaging/check_2k5_mod_studio_runtime.py`, `packaging/release-allowlist.txt`: exact owner/data pins, runtime module and two allowlist entries.
- `mod_editor/capabilities/registry.v1.json`: updates only `nfl2k5.presentation.modern_color_lighting`; existing incorrect haze summary corrected; scope and evidence expanded. `reports/b71_c3/registry-row.json` records the row.
- `docs/mod_editor/2k5_mod_studio_changelog.md`: RC96 bullet, no reporter names or prompting history. Controls documented in `docs/modern_color/CONTROLS.md`.
- New colour core and offscreen suites; Build publication and provider isolation regression tests; read-only exhaustive default-pin verifier.

The brief authorizes these GUI, build, owner, registry and packaging changes, so they are wired directly despite the older context's generic protected-file list. The shared cave manifest is unchanged because ownership/spans are unchanged; run the normal manifest regeneration during stack integration as required by ASTRA_CONTEXT.md.

## Verification commands

Commands run from this worktree with `PYTHONPATH=<worktree>` and `QT_QPA_PLATFORM=offscreen`. `.scratch/run_check.py` records UTC start, process exit and monotonic elapsed seconds; full output is in `reports/b71_c3/`. Both XBE gates ran as detached subprocess session leaders (`start_new_session=True`) under durable tool sessions. The initial fire-and-forget launch was reaped by its tool context and was replaced by these tracked runs.

| Log | Command | Exit | Seconds | UTC start |
|---|---|---:|---:|---|
| [colour_initial](reports/b71_c3/colour_initial.log) | `python3 tests/mod_editor/test_nfl2k5_modern_color.py` | 0 | 8.093 | 2026-09-15T19:01:08.726999+00:00 |
| [build_panel_initial](reports/b71_c3/build_panel_initial.log) | `python3 tests/mod_editor/test_build_panel_qt.py` | 0 | 4.324 | 2026-09-15T19:06:11.082618+00:00 |
| [mod_build_initial](reports/b71_c3/mod_build_initial.log) | `python3 tests/mod_editor/test_mod_build.py` | 1 | 1.792 | 2026-09-15T19:06:32.373707+00:00 |
| [repin_initial](reports/b71_c3/repin_initial.log) | `python3 packaging/repin.py --apply` | 0 | 22.163 | 2026-09-15T19:07:05.518737+00:00 |
| [repin_checkpoint](reports/b71_c3/repin_checkpoint.log) | `python3 packaging/repin.py --apply` | 0 | 22.424 | 2026-09-15T19:07:46.651584+00:00 |
| [colour_controls_initial](reports/b71_c3/colour_controls_initial.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 0 | 13.620 | 2026-09-15T19:09:40.524497+00:00 |
| [colour_gui_initial](reports/b71_c3/colour_gui_initial.log) | `python3 tests/mod_editor/test_colour_lighting_qt.py` | 0 | 1.293 | 2026-09-15T19:11:01.385744+00:00 |
| [xbe_memory_writes](reports/b71_c3/xbe_memory_writes.log) | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 0 | 1629.920 | 2026-09-15T19:12:16.225386+00:00 |
| [xbe_cave_references](reports/b71_c3/xbe_cave_references.log) | `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 0 | 1822.416 | 2026-09-15T19:12:16.243111+00:00 |
| [all_default_pins](reports/b71_c3/all_default_pins.log) | `python3 tools/verify_colour_lighting_pins.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --workers 8` | 0 | 390.999 | 2026-09-15T19:14:58.232963+00:00 |
| [mod_build](reports/b71_c3/mod_build.log) | `python3 tests/mod_editor/test_mod_build.py` | 0 | 2.750 | 2026-09-15T19:15:59.568969+00:00 |
| [repin_final](reports/b71_c3/repin_final.log) | `python3 packaging/repin.py --apply` | 0 | 33.776 | 2026-09-15T19:16:57.892651+00:00 |
| [registry_strict](reports/b71_c3/registry_strict.log) | `python3 -m mod_editor.capabilities.validate_registry` | 1 | 0.285 | 2026-09-15T19:17:31.837170+00:00 |
| [provider_integrity](reports/b71_c3/provider_integrity.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 5 | 0.376 | 2026-09-15T19:17:31.890817+00:00 |
| [product_catalog](reports/b71_c3/product_catalog.log) | `python3 tests/mod_editor/test_product_catalog.py` | 5 | 0.236 | 2026-09-15T19:17:31.891870+00:00 |
| [phase1_packaging](reports/b71_c3/phase1_packaging.log) | `python3 tests/mod_editor/test_phase1_packaging.py` | 0 | 2.902 | 2026-09-15T19:17:31.919774+00:00 |
| [colour_legacy](reports/b71_c3/colour_legacy.log) | `python3 tests/mod_editor/test_nfl2k5_modern_color.py` | 0 | 8.024 | 2026-09-15T19:17:31.938804+00:00 |
| [colour_controls](reports/b71_c3/colour_controls.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 0 | 21.533 | 2026-09-15T19:17:31.988748+00:00 |
| [colour_gui](reports/b71_c3/colour_gui.log) | `python3 tests/mod_editor/test_colour_lighting_qt.py` | 0 | 2.283 | 2026-09-15T19:17:32.030445+00:00 |
| [build_panel](reports/b71_c3/build_panel.log) | `python3 tests/mod_editor/test_build_panel_qt.py` | 0 | 4.330 | 2026-09-15T19:17:32.056547+00:00 |
| [product_catalog_retry](reports/b71_c3/product_catalog_retry.log) | `python3 tests/mod_editor/test_product_catalog.py` | 0 | 0.254 | 2026-09-15T19:18:18.203805+00:00 |
| [provider_integrity_retry](reports/b71_c3/provider_integrity_retry.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 1 | 12.473 | 2026-09-15T19:18:18.223985+00:00 |
| [repin_provider](reports/b71_c3/repin_provider.log) | `python3 packaging/repin.py --apply` | 0 | 21.043 | 2026-09-15T19:20:03.226498+00:00 |
| [registry_strict_hydrated](reports/b71_c3/registry_strict_hydrated.log) | `python3 -m mod_editor.capabilities.validate_registry` | 0 | 0.264 | 2026-09-15T19:20:54.919117+00:00 |
| [repin_closure](reports/b71_c3/repin_closure.log) | `python3 packaging/repin.py --apply` | 0 | 14.120 | 2026-09-15T19:21:48.767309+00:00 |
| [project_settings_regression](reports/b71_c3/project_settings_regression.log) | `python3 tests/mod_editor/test_discord_bugs_1.py` | 0 | 1.854 | 2026-09-15T19:22:33.589016+00:00 |
| [provider_integrity_final](reports/b71_c3/provider_integrity_final.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 1 | 13.290 | 2026-09-15T19:22:33.599368+00:00 |
| [product_catalog_final](reports/b71_c3/product_catalog_final.log) | `python3 tests/mod_editor/test_product_catalog.py` | 0 | 0.212 | 2026-09-15T19:22:33.629593+00:00 |
| [phase1_packaging_final](reports/b71_c3/phase1_packaging_final.log) | `python3 tests/mod_editor/test_phase1_packaging.py` | 0 | 2.792 | 2026-09-15T19:22:33.639025+00:00 |
| [repin_verified](reports/b71_c3/repin_verified.log) | `python3 packaging/repin.py --apply` | 0 | 24.745 | 2026-09-15T19:24:29.687611+00:00 |
| [provider_integrity_pass](reports/b71_c3/provider_integrity_pass.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 0 | 10.719 | 2026-09-15T19:25:03.637296+00:00 |
| [providers_regression](reports/b71_c3/providers_regression.log) | `python3 tests/mod_editor/test_providers.py` | 0 | 3.927 | 2026-09-15T19:25:03.660747+00:00 |
| [registry_strict_final](reports/b71_c3/registry_strict_final.log) | `python3 -m mod_editor.capabilities.validate_registry` | 0 | 0.167 | 2026-09-15T19:25:03.669295+00:00 |
| [repin_receipts](reports/b71_c3/repin_receipts.log) | `python3 packaging/repin.py --apply` | 0 | 20.248 | 2026-09-15T19:28:00.624628+00:00 |
| [colour_controls_final](reports/b71_c3/colour_controls_final.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 0 | 14.064 | 2026-09-15T19:28:01.806796+00:00 |
| [colour_legacy_final](reports/b71_c3/colour_legacy_final.log) | `python3 tests/mod_editor/test_nfl2k5_modern_color.py` | 0 | 6.619 | 2026-09-15T19:28:01.825264+00:00 |
| [provider_integrity_verified](reports/b71_c3/provider_integrity_verified.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 0 | 10.001 | 2026-09-15T19:31:01.714288+00:00 |
| [repin_display_defaults](reports/b71_c3/repin_display_defaults.log) | `python3 packaging/repin.py --apply` | 0 | 22.075 | 2026-09-15T19:41:52.525425+00:00 |
| [colour_gui_verified](reports/b71_c3/colour_gui_verified.log) | `python3 tests/mod_editor/test_colour_lighting_qt.py` | 0 | 1.641 | 2026-09-15T19:41:53.705972+00:00 |
| [colour_legacy_verified](reports/b71_c3/colour_legacy_verified.log) | `python3 tests/mod_editor/test_nfl2k5_modern_color.py` | 0 | 8.277 | 2026-09-15T19:41:53.727357+00:00 |
| [colour_controls_verified](reports/b71_c3/colour_controls_verified.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 0 | 13.711 | 2026-09-15T19:41:53.739908+00:00 |
| [provider_integrity_delivery](reports/b71_c3/provider_integrity_delivery.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 0 | 9.961 | 2026-09-15T19:42:17.258466+00:00 |
| [build_panel_delivery](reports/b71_c3/build_panel_delivery.log) | `python3 tests/mod_editor/test_build_panel_qt.py` | 0 | 2.916 | 2026-09-15T19:43:54.470105+00:00 |
| [mod_build_delivery](reports/b71_c3/mod_build_delivery.log) | `python3 tests/mod_editor/test_mod_build.py` | 0 | 1.878 | 2026-09-15T19:43:54.480260+00:00 |
| [phase1_delivery](reports/b71_c3/phase1_delivery.log) | `python3 tests/mod_editor/test_phase1_packaging.py` | 0 | 2.127 | 2026-09-15T19:43:54.502872+00:00 |
| [registry_delivery](reports/b71_c3/registry_delivery.log) | `python3 -m mod_editor.capabilities.validate_registry` | 0 | 0.158 | 2026-09-15T19:43:54.516878+00:00 |

Intermediate failures were retained rather than hidden:

- The initial ModBuild run found an unnecessary executable read in the new Off preflight for synthetic/non-disc sources. The read now handles an unavailable executable; the full 13-test suite passes.
- Registry/provider/catalog initially rejected noncanonical JSON; it was reserialized using the validator's exact sorted JSON format.
- Strict validation initially lacked 75 pre-existing evidence documents in this worktree. The local inventory supplied 72 research Markdown files and three metadata-only JSON/GLTF documents as read-only copies. No GLTF buffer, retail executable, disc, pack or other retail payload was copied. The source inventory was not changed; hydrated evidence is excluded from commits. `evidence-hydration.json` lists each copied file and hash.
- Provider integrity exposed the newly reachable owner missing from its closure. Added the exact source pin, its existing data pin and the 286-module expectation. The first isolated test used this worktree's retail symlink and correctly hit the evidence-root gate; it now uses the existing clean-provider fixture. The complete integrity suite and the 33 provider tests pass.

## Review artifacts and witness recipe

- [Turf controls](reports/b71_c3/colour-controls.png) and [light controls](reports/b71_c3/light-controls.png): inspected offscreen captures.
- [Custom bundle proof](reports/b71_c3/bundle-parameter-proof.json): hashes, changed sites, fit/scratch receipts and palette changes; no retail asset bytes.
- A player should compare Broadcast against custom settings at one matched camera/resolution, then exercise day, afternoon, night/dome, rain and snow. Check whites/skin, painted end-zone art, sideline brightness, existing stripes, far-field noise, and any span reported unfit. Save/reload the project before the second build and keep its receipt next to the output disc.

## Commits

- `24d08de9 Normalize the displayed Broadcast bump default without changing its bytes`
- `c7281ddc Keep colour replay and disabled-tint receipts accurate`
- `a9df0a53 Verify custom lighting receipts, pin the provider closure, and document the controls`
- `5bc7100b Add project colour and lighting controls through the v2.1 owner`

A final report/evidence commit follows these implementation commits. The bundle includes that final commit.

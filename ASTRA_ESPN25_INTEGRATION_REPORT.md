# ESPN 25th Anniversary integration into the protected Studio files, 2026-09-07

Done by Claude Fable 5.1 (the file keeps the ASTRA_ name the brief asked for). Branch
`fable/r64-espn25-integration`, base `4d4f96e`. EXPERIMENTAL / UNWITNESSED: no game was
played, no disc image was built outside the synthetic test fixtures, and nothing was pushed.

## What was wired where

| Protected surface | Change |
|---|---|
| `mod_editor/gui/roster_editor_panel_qt.py` | Imports `Espn25Panel`; adds the Rosters subtab **ESPN Anniversary** (index `_espn25_index`, disabled until a supported disc image loads; the tab bar stays visible even while the Franchise page hides itself). `load_document(kind="disc")` starts `_Espn25CatalogTask` (a `QRunnable` on the global `QThreadPool`) that runs `Catalog.load(source)` off the GUI thread; the detached catalog comes back through a signal and `set_catalog` runs on the GUI thread. A layout refusal disables the tab, writes the reason into the tab tooltip and the host status line (`load_disc`'s own error path). A generation counter drops results of superseded loads. Pending edits: `espn25_dirty()` joins `is_dirty()`, so the shell's "an edited roster is never reset" guard and the Replace prompt (now naming the Anniversary edits) protect them; only an explicit load replaces the catalog. `plan_ready` -> `_espn25_plan_ready`: `espn25_plan_path`, `espn25_plan_changed(str)` signal, saved-state baseline, status hint. `espn25_recovery_snapshot()` (JSON-safe: identity digests, `panel.pending`, `scenario_json`, plan path) and `restore_espn25_recovery()` (queued until the catalog loads, applied only when the SITU / historic roster / descriptor digests match, every CSV re-validated). `show_espn25()` for the Gameplay page action. |
| `mod_editor/gui/text_rosters_panel.py` | `ESPN_25TH_COMING_SOON_NOTE` replaced with the WIRING text verbatim. New `SITU_BANK_PREFIX` and `TextRosterPanel.anniversary_pending_edits()` (asset ids of SITU strings whose staged value differs from the disc) for the conflict rule. The four-string editor is untouched and fixed at 25. |
| `mod_editor/core/mod_build.py` | `BuildPlan.espn25_plan: str = ""` beside `roster_edits`; `""` in basic, advanced and experimental presets. `availability()["espn25_plan"]` from `_core_module("nfl2k5_espn25_scenarios")`. `inspect()`: `"requires image"` for a bare XBE; images probed with `Catalog.load` -> `available` / `foreign` (never the plan-dependent `status`). `_build`: type check + strip; then, once the container is known: bare-XBE refusal, refusal with the roster arena growth (`reserves_16` / `created_teams_extra`, the version-18 wrapper geometry), refusal with `position_pools` (the reclassify recodes outer 113..187 by default: `tools/nfl2k5_roster_reclassify.py` `HISTORIC_ROST_ENTRIES = range(113, 188)`, `historic=True`), missing-file refusal, then `read_json` exactly once and `resolve_plan(Catalog.load(source), loaded)` before any copy (message prefixed `ESPN Anniversary plan refused:`). Final pass after the OLB filter pass and the final re-inspection, before `build()` publishes: exactly the WIRING block (`progress("Applying ESPN Anniversary edits", 0, 0)`, `apply_to_image`, `steps.append({"step": "espn25_plan", **receipt})`, `result["espn25_plan"] = status(...)`) plus a refusal if the read-back is not `applied`. Never `build_image`. |
| `mod_editor/gui/gameplay_patches_panel_qt.py` | `PATCHES` row `espn25_plan` (WIRING text verbatim), `LABELS` entry, `NEEDS_IMAGE.add("espn25_plan")`, `INFORMATIONAL = {"espn25_plan"}`: the row is a caption plus an **Open Rosters > ESPN Anniversary** button emitting `open_anniversary`; it never creates a `QCheckBox`, so `plan()` cannot pass a Boolean through the path field. `apply_state` gives it the badge only (`Full disc required` / `Unrecognized source data`). |
| `mod_editor/gui/build_panel_qt.py` | `_option(r, "espn25_plan", "Use saved ESPN Anniversary edits", ...)` with the content-file row (`espn25_plan_field`, Choose..., status label) mirroring `roster_edits`; `set_espn25_plan(path)` / `_choose_espn25_plan()`; `_espn25_plan_problem()` validates the file shape through the bounded reader (cached per path/size/mtime); `blocker()` names a missing or invalid plan; `plan()` carries the path only while ticked (unticking clears `espn25_plan`); `_boxes()`, `has_work()`, the read-back bits and the confirmation file list include it; `apply_state` enables the box only for an image whose probe says `available`. Presets never tick it (`""`). |
| `mod_editor/gui/studio_qt.py` (forwarding hooks only) | `roster_editor.espn25_plan_changed -> _espn25_plan_saved` (sets the Build field/box, then `_gameplay_build_changed()` = capture build settings + mark the workspace dirty + autosave); `gameplay_patches_panel.open_anniversary -> _open_rosters_anniversary` (`_go_to_rosters()` + `show_espn25()`); the Build `operation_guard` now also runs `_espn25_text_conflict()`, which refuses a build that includes the shared project while Game Text has pending SITU strings and the plan is ticked, naming the count, before the build starts. |
| `packaging/release-allowlist.txt` | The seven WIRING lines, after `mod_editor/gui/roster_editor_panel_qt.py`. No tests, no private helpers. |
| `packaging/check_2k5_mod_studio_runtime.py` | `mod_editor.core.nfl2k5_espn25_scenarios` and `mod_editor.gui.espn25_panel_qt` in the closure import exercise; layout pins checked relative to the installed root (`MANIFEST` path, 75 roster pins, `REQUESTS == ()`, plan schema); the Rosters host must start with the subtab disabled; an `Espn25Panel` is constructed offscreen and closed. Count pins 113 / 75 and the summary string. |
| `mod_editor/capabilities/registry.v1.json` | The single object from `docs/mod_editor/nfl2k5_espn25_capability.json` inserted at index 49 (between `nfl2k5.equipment.guardian_overlay` and `nfl2k5.franchise.practice_squad_screen`), written as `json.dumps(data, indent=2, sort_keys=True) + "\n"`. 113 rows. |
| Count pins | `check_apf2k8_mod_studio_runtime.py` 113; `test_apf_studio_installer.py` 113; `test_phase1_packaging.py` 113 / 75; `test_product_catalog.py` id set + 75, `ROSTERS_PLAYERS (9, 9, 0, 0, 0, 0, 0)`, global `(75, 56, 8, 1, 0, 7, 3)`; `docs/mod_editor/2k5_mod_studio_getting_started.md` 113 / 75. |
| `mod_editor/core/providers.py` | `repin.py --apply` refreshed the pins of `mod_build.py` and `nfl2k5_build_settings.py` (and four pins that were already stale at HEAD, see below). No new closure member: `mod_build` reaches the feature through `_core_module`, so `test_provider_integrity` passes with its literal unchanged. |

Two unlisted files needed one line each, or the project could not save at all: `BuildPlan.to_recipe()`
feeds `nfl2k5_build_settings.build_settings`, which rejects any key outside `FEATURE_KEYS`, so
`espn25_plan` joins `FEATURE_KEYS` (`mod_editor/core/nfl2k5_build_settings.py`, the same edit the
OLB integration made for its key) and the Build field joins the restore tuple in
`mod_editor/gui/gameplay_project_ui.py`. That is what persists and recovers the plan path with a
named or recovery project. Tests changed by the integration: `test_gameplay_patches_panel_qt.py`
(PATCHES key list), `test_text_rosters_panel.py` (the three note assertions now check the WIRING
text), `test_product_catalog.py`, `test_phase1_packaging.py`, `test_apf_studio_installer.py`.
New suite: `tests/mod_editor/test_nfl2k5_espn25_integration_qt.py` (13 tests: presets and
persistence, bare-XBE and image inspection, the four validation refusals before any copy, the
final pass on the copy with the source left `ready` and a failing pass discarding the output,
the subtab lifecycle, layout refusal, dirty tracking, recovery snapshot/restore against matching
and foreign catalogs, the Replace prompt, the informational Gameplay row, the Build option with
its picker/blocker/presets/persistence, and the SITU conflict helper).

Not touched: `nfl2k5_throw_tuning.py` (no dispatcher entry, kwarg, tuple entry, adapter or status
key), `data/nfl2k5_cave_reservations.json`, the four XBE-only status dictionaries, any owner
module. `REQUESTS = ()` stays. The modpack exporter derives its operations from image diffs and
the recipe (`receipt["plan"]` holds only the plan path), so the plan's before-byte preimages in
the local receipt step never reach a public pack.

## Steps that could not be done exactly as written

1. **Count pins 111->112 / 73->74.** Commit `3cdb41c` (the OLB wiring) had already taken the
   registry to 112 rows / 74 NFL 2K5 capabilities on this stack, so this integration takes them
   to **113 / 75** everywhere they are asserted.
2. **"(31 characters)".** The caption is used verbatim, `Use saved ESPN Anniversary edits`; it is
   32 characters. The new suite pins the verbatim caption.
3. **Recovery snapshot of `panel.pending`.** The shell's ordinary unsaved-edit recovery is the
   project archive, whose only free-form slot is `build_settings`, strictly typed to BuildPlan
   fields (`mod_editor/studio/project_archive.py` and `facade.py` are outside the allowed set).
   The plan **path** is recovered with the project through that slot. The in-memory pending
   grid edits and scenario JSON are protected from routine refreshes by the host's dirty guard
   and exposed through `espn25_recovery_snapshot()` / `restore_espn25_recovery()` (identity
   matched, CSV re-validated, tested), ready for the archive to carry once it gains a slot; the
   durable artifact today is the atomically saved plan file, like the ★ Rosters export.
4. **Portable project preservation of the plan file.** Same boundary: the archive stores paths
   only (as it does for `roster_edits`); the plan path is stored as saved and a missing or
   foreign file is named by the Build blocker rather than resolved relative to the project.
5. **Unticking.** Unticking clears `BuildPlan.espn25_plan` (the plan carries `""`); the path text
   stays in the field for re-ticking, the `roster_edits` behaviour.
6. **Registry validator file audit.** This fresh worktree lacked 161 gitignored release inputs
   (`reports/assets/`, `tools/vendor/`, `research/`, 356 MB) that the main checkout and the
   beta-62 worktree carry; without them the validator's file audit, `test_phase1_packaging`,
   `test_apf_studio_installer`, `test_no_capability_is_invisible` and both stage_release runs
   refuse on the same pre-existing gap Astra's report noted. They were copied from
   `/home/noah/2k-football-mod-tools` (read only there; all gitignored here, nothing committed).
   With them present every check passes with the file audit on.
7. **Pre-existing stale pins.** `repin.py --apply` also corrected four provider pins that no
   longer matched their files at HEAD (`nfl2k5_throw_tuning.py`: pin `d491d9d9...`, file
   `d1ac966a...`; likewise `nfl2k5_position_pools.py`, `nfl2k5_practice_squad_screen.py`,
   `nfl2k5_probowl_order.py`). repin only recomputes from the bytes a pin covers; nothing was
   relaxed. `test_provider_integrity` passes.

## Verification (all offscreen, worktree as cwd, `PYTHONPATH=.`)

| Command | Result |
|---|---|
| `tests/mod_editor/test_nfl2k5_espn25_scenarios.py` | 17 passed |
| `tests/mod_editor/test_nfl2k5_espn25_native.py` | 7 passed |
| `tests/mod_editor/test_nfl2k5_espn25_panel_qt.py` | 5 passed |
| `tests/mod_editor/test_nfl2k5_espn25_integration_qt.py` (new) | 13 passed |
| `tests/mod_editor/test_roster_editor_panel_qt.py` | 50 run, 49 passed, 1 skipped (portrait catalogue absent, as before) |
| `tests/mod_editor/test_roster_editor_panel_franchise.py` | 2 passed |
| `tests/mod_editor/test_text_rosters_panel.py` | 14 passed |
| `tests/mod_editor/test_gameplay_patches_panel_qt.py` | 1 passed |
| `tests/mod_editor/test_ux_build_plan_coverage_qt.py` | 7 passed |
| `tests/mod_editor/test_beta62_integration3_qt.py` | 8 passed |
| `tests/mod_editor/test_discord_bugs_1_wiring.py` | 10 passed |
| `tests/mod_editor/test_product_catalog.py` | 9 passed |
| `tests/mod_editor/test_provider_integrity.py` | 7 passed |
| `tests/mod_editor/test_phase1_packaging.py` | 17 passed |
| `tests/mod_editor/test_apf_studio_installer.py` | 16 passed |
| `tests/mod_editor/test_no_capability_is_invisible.py` | 14 passed |
| `tests/mod_editor/test_capability_registry_module_commands.py` | 3 passed |
| `tests/mod_editor/test_apf_public_docs_registry_current.py` | 5 passed |
| `tests/mod_editor/test_nfl2k5_roster_records.py` | 108 passed |
| `tests/test_nfl2k5_safe_text_banks.py` | 9 passed |
| `mod_editor/capabilities/validate_registry.py` (file audit on) | PASS, capabilities=113 |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 91 passed, 357 s |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 103 passed, 434 s |
| `stage_release.py release-allowlist.txt <scratch>/stage .` + `check_2k5_mod_studio_release.py` + `check_2k5_mod_studio_runtime.py` (in the stage) | rc 0 / 0 / 0: `2K5_MOD_STUDIO_RELEASE_PASS files=695`, `2K5_MOD_STUDIO_RUNTIME_CLOSURE_PASS ... registry=113 sections=12 nfl2k5_capabilities=75` |
| `stage_release.py apf2k8-release-allowlist.txt` + `check_apf2k8_mod_studio_release.py` + `check_apf2k8_mod_studio_runtime.py` | rc 0 / 0 / 0: `APF2K8_MOD_STUDIO_RELEASE_PASS files=206`, `APF2K8_MOD_STUDIO_RUNTIME_PASS modules=104 capabilities=37` |
| `git diff --check` | clean |

No disc image was built; the only images were the sub-4 MiB synthetic fixtures in temporary
directories, removed by the tests. The scratch stages were deleted after the checks.

## The GUI flow for Noah

1. Open your USA disc image (top right). On **★ Rosters** the page reads the roster as before and,
   off-thread, the Anniversary scenarios and 75 historic rosters; the **ESPN Anniversary** subtab
   enables when that succeeds (a save, a bare XBE or a foreign layout leaves it disabled and says
   why in the tab tooltip and the status line).
2. Open **Rosters > ESPN Anniversary**. Pick a moment (1..25) and a side (Away / Home). The label
   names the historic team and year and every other moment that shares that roster file.
3. Tick **I understand that every use of this historic roster will change** (the shared-use
   acknowledgment). Edit cells directly (names, numbers, positions, ratings, appearance,
   equipment) or **Import roster CSV** (`pool,index` plus any exported columns; a bad file is
   refused whole). **Export roster CSV** gives a template. Optional: **Load scenario JSON** or type
   `nfl2k5.espn25.edits.v1` setup edits (scores, clock, field position, sides, conditions) in the
   box.
4. **Save build edits**: the plan is validated against the open disc and written atomically. The
   status line confirms and ★ Build & Share ticks **Use saved ESPN Anniversary edits** with the
   plan path (it can also be chosen by file). The project remembers it.
5. On ★ Build & Share pick a new output name and **Make my disc**. Anniversary edits run last of
   all passes on the copy; the source disc is never written. If Game Text has pending Anniversary
   strings and the shared project is included, the build button says so before starting. The
   receipt's last step is `espn25_plan` and `result.espn25_plan` is `applied`.
6. Not combinable in one build: the merged position pools (they recode the historic rosters) and
   the 16-reserve / extra-team arena growth (they change the pinned main-roster geometry).
   Rebuild from the retail disc or leave those off. Editing a historic roster changes every moment
   that uses it and that team outside Anniversary mode. Extra moments validate for research only;
   nothing installs more than 25.

Witness list: unchanged from `ASTRA_ESPN25_SCENARIOS_REPORT.md` (items 1-7). Nothing here claims a
played game.

# Beta 66.1 H1: 2K5 workspace, stalls, kit import and build proof

Branch: `astra/b661-tool`. Base: `1d38df5e782ffe8115ed38e82c4c639c04b1d3b5`.
Implementation commit: `84c3df18` (`Fix beta 66.1 workspace stalls and prove kit equipment builds`).
The resumed work was reviewed and retained where correct. The fixes and tests are
committed with explicit paths. Git metadata accepted the commit, so no bundle is needed.

**Integration status:** core changes and the permitted one-line page-selection fix are
applied. The other protected GUI changes, startup hook and four release-allowlist entries
are complete code blocks in [WIRING.md](WIRING.md). The first-page tests and retail replay
execute those exact blocks on the real `StudioMainWindow` in memory. They are not a
claim that the protected integration has already shipped.

## PROVED

- **First Uniforms visit completes without switching pages.** The cold and cached
  synthetic source-open tests deliver a populated component list and actual preview;
  the final maximum UI gaps were **94 ms / 68 ms**, against a **250 ms** assertion.
  Pending preparation keeps a heartbeat. A failed preparation offers Retry; finishing
  in the background preserves whichever page the user selected meanwhile.
- **Read-only retail-cache replay:** real `Nfl2k5StudioFacade`, real source identity
  authentication, real catalogs, real preview decoding, real `StudioMainWindow`,
  Uniforms selected first. Disc open took **15.501 s**, page plus preview **0.660 s**,
  and remaining startup workers settled in **8.438 s**. Build inspection also finished.
  The maximum UI gap across opening and preparation was **148.782 ms**. The following
  **120.000 s** idle period peaked at **23.655 ms**. **Zero stalls over 200 ms**, no
  errors, selected row and visible row both 1. This is one Linux offscreen measurement,
  not a cross-platform latency guarantee or a matched retail speedup benchmark.
- **Kit pixels reach the built package.** Export 39 components, edit the torso PNG,
  import one change / skip 38 unchanged, inspect the session and selected GUI preview,
  write the canonical project, then run the actual backend `build` command handler in
  a fresh interpreter with synthetic source identities. One separate synthetic shoe
  edit is included. The tool's own `_load_uniform_equipment_adapter()` loads the writer
  as `_nfl2k5_uniform_equipment_unified_adapter` with no package. Both receipt entries
  exist and both built spans decode to every expected RGBA byte; the source is unchanged.
  Alpha-only edits and indexed-palette changes are separately proved not to be skipped.
- **Manual update refusal:** an unsupported manual tree, source ZIP with launchers and
  incomplete Windows Setup layout all refuse before download or installer launch. The
  existing supported installer/portable-layout and updater suites also pass.
- **Verification:** 35 standalone unittest suites, **353 tests run: 351 passed, 2 precise
  optional-evidence skips**. The exact commands and complete outputs are in
  [commands.txt](reports/b661_h1/commands.txt), [validation.log](reports/b661_h1/validation.log)
  and [validation.json](reports/b661_h1/validation.json). `repin.py --apply` is clean.

## Root causes and final changes

### Loading workspace / nonresponding window (triage row 2)

I inspected both supplied Discord screenshots, `2k5-bugs_003.png` and `_004.png`.
They show Uniforms selected, only the loading placeholder, and the Windows title
“2K5 Mod Studio (Non risponde)”. maumau78 wrote “after switching to another section it
works”; Coach Edwards wrote “The Loading Workspace screen is just stuck”.

1. `mod_editor/gui/studio_qt.py:2799` removes the selected placeholder from the
   `QStackedWidget`. Qt selects the next widget. Reinserting at the same index does
   not select the new page. The cached/synchronous `_ensure_workspace` path had no
   final selection restoration. The asynchronous `ready` callback already did restore
   selection; this was not a universally missing completion signal. The allowed
   one-line fix at line 2802 restores `navigation.currentRow()` immediately after
   insertion. Replaying the base implementation against the new real-window test
   reproduces **visible row 2 != selected row 1** on the cached path.
2. Base `mod_editor/studio/facade.py:3196` held the facade state lock while
   `session.current_path()` decoded a cold preview. UI getters such as `source_ready`
   and `modified_count` also need that lock. The baseline reproduction blocks a getter
   for approximately **505 ms** until the test decoder is released. The final
   `preview_asset` at line 3203 takes a session/staged-path snapshot and releases the
   UI state lock before decoding. It rechecks source identity and staged precedence
   on return. `uniform_colors` at line 3082 follows the same principle for its first
   archive read. The original PNG and its hash receipt have a separate IO lock in
   both uniform and extended visual IO, with a concurrent preview/export test.
3. Large C JSON calls in `metadata_cache.read/write`, uniform authored-digit metadata,
   extended visual reports and the repeated inventory reads could hold the interpreter
   lock even inside a Qt worker. `responsive_json.py` decodes metadata arrays by row,
   yields between batches, and writes compact metadata incrementally. Output bytes
   match the previous compact encoder. Asset IO, text catalogs, roster and scene
   parsers share `nfl_uniform_inventory.load_inventory_document`. Its first row-index
   construction (`_InventoryRows.rows_for`, around line 261) yields every 512 rows.
4. `studio_qt.py::_prefill_panels_from_source` formerly started full Build inspection,
   Models and Animations on source open. WIRING moves Build inspection into a child
   interpreter through `core/studio_inspection.py`; hidden Models/Animations load on
   entry. The child preserves `TuningSettings` as the actual dataclass expected by
   Build, and is tested against complete in-process synthetic inspection. Errors
   update the status as well as any constructed Build panels.

The heavy metadata/IO preparation remains outside the UI thread. Whole-page Qt widget
construction/painting is included in the measured 149 ms gap; I do not claim every Qt
callback runs within 50 ms. The requested 250 ms open/first-page watchdog bound is proved
by both the deterministic test and the measured retail-cache replay.

The controlled baseline reproduction is preserved independently of later commits:

```sh
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 reports/b661_h1/prove_regressions.py
```

It loads only the two original methods from the fixed base commit, in memory. Expected
assertion failures are followed by `EXPECTED_REGRESSION_REPRODUCED` for each case;
[regressions.log](reports/b661_h1/regressions.log) contains the exact output.

### Periodic hangs (triage row 3)

Ju3tin: “the program keeps hanging every 20 secs or so”. I did **not** reproduce a
recurring 20-second idle event. Startup contention was real: the earlier resumed probe
still had a 400 ms first-preview pause. Incremental inventory/cache work and releasing
the colour-read lock removed that pause in the final replay. A blanket claim that
Ju3tin's exact Windows problem is fixed would exceed the evidence.

The timer/thread audit covers each beta-66 suspect:

| Activity | Source / schedule | Evidence in this first-page replay |
|---|---|---|
| Uniforms/visual catalogs | `studio_qt.py:2811`, `_BackgroundTask` on first entry | Worker preparation; content completes without another navigation signal |
| Build options / ESPN 2025 CSV tables | same `prepare`, `mod_build.availability()` | Demand-driven first Build/Gameplay entry, no periodic timer; never entered in this replay |
| Full Build source inspection | `_prefill_panels_from_source` worker | Runs once after open in the child process; typed state arrived successfully |
| Scorebar preview | `scorebug_studio_panel_qt.py:163,914` | One-shot on first show and 80 ms coalescing after edits; Scorebar remains unconstructed here |
| Metadata cache refresh | `core/metadata_cache.py` | No timer; keyed reads/rebuilds during catalog preparation |
| Update check | `studio_qt.py:1857`, `update_ui.py:129` | One-shot at 1200 ms, pool worker if enabled; disabled with `MOD_STUDIO_NO_UPDATE_CHECK=1` for this offline probe |
| Shell/build heartbeat | `studio_qt.py:1843,8126`, `build_panel_qt.py:116,2255` | One-second label updates while busy; 15 shell timer firings logged, then inactive; Build panel never constructed |
| Diagnostic | `gui/stall_watchdog.py` | 20 ms precise heartbeat, 25 ms background sampling, 5 s activity inventory; no active app worker at idle |
| Garbage collection | `gui/workspace_runtime.py` | CPython old-generation threshold raised to at least 100; young generation unchanged; one collection over 50 ms logged during preparation, zero resulting stalls |

`MOD_STUDIO_STALL_LOG=1` installs the hidden diagnostic via WIRING. It writes
`stalls.jsonl` beside `errors.log` in `crash_report.log_directory("2K5 Mod Studio")`.
The writer runs on the sampler thread and rotates at 8 MiB. Each sampled stall retains
UI and worker Python stacks; a recovered heartbeat gap is separately labelled when
native code held the GIL and prevented sampling. Timer discovery is batched (64 objects /
5 ms), because profiling found that a recursive Qt `findChildren(QTimer)` diagnostic
call itself could take 470 ms. Off by default means no diagnostic timer/thread/file.
The opt-in test records a deliberate 320 ms block, the blocked function's stack and a
named timer firing. This cannot diagnose a hang before the app can start.

Exact final retail command:

```sh
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tools/studio_stall_probe.py --seconds 120 --pending-wiring --output /tmp/b661-h1-resume/acceptance.json
```

Complete result: [acceptance.json](reports/b661_h1/acceptance.json). All stacks, GC and
activity records: [acceptance.jsonl](reports/b661_h1/acceptance.jsonl).
The probe exits 77 with an explicit reason for an absent retail disc/indexed cache.
It authenticates and reads existing cache packs in place, uses temporary derived
metadata/original previews/sessions, and cleans them up. It does not copy a retail disc
or mutate the existing cache. The private Stadium cache is deliberately not attached.

### Import edited kit and equipment builds (triage rows 4 / 1)

Coach Edwards: “Import Edited Kit ... then nothing actually changes”. I inspected
`attachments/2k5-bugs_f8e378c5_1.jpg`: it shows “Imported: 10. Skipped unchanged: 29.
Overwritten: 0.” and Modified components, but does not establish which pixels Coach
expected to see or what reached a build.

Trace exercised by `test_b661_kit_build.py` and `test_b661_workspace_qt.py`:
`facade.export_team_kit_sets` → `TeamKitBundleService.export` → edited folder PNG →
`facade.import_team_kit` / `import_edited` → `session.replace_batch` and staged path →
GUI import-button success / refreshed selected-component pixmap → canonical project →
`tools/nfl2k5_visual_mod_project.py::main` (`build`) → manifest and fixed output spans →
independent decoding of both jersey and shoe pixels.

No stale-pixel comparison or missing-build-edit defect reproduced in these lanes.
Decoded RGBA comparison already included alpha and palette expansion. The preview
state-lock defect above was separate, and Claude's path-loaded writer fix in the base
commit is exercised end to end, not assumed to explain the entire report. The summary
now lists the staged component names and says **“Build Modded XISO to apply these edits
to a new game disc.”** Neither import nor its receipt claims the source disc changed.

The CLI test substitutes synthetic source identities and target metadata only. It
keeps production archive parsing, the tool's own adapter loader, PNG encoders, fixed-span
writes, source preservation, union verification and receipt publication. Output:

```text
NFL2K5_VISUAL_MOD_BUILD_PASS edits=2 changed=2701 kept_retail=0 sha256=fd59d6db8539da7c1cadb66586635c4064f9eebf0859bdff0cb8bd50077d719f runtime=false
```

### Manual installation updater (triage row 7)

GoldenTiger's manual-install/update failure and Noah's advice to “run the setup.exe”
are addressed in `core/self_update.py:126` (`detect_install`) and `plan_update`.
Unsupported layouts now get:

> This copy was not installed with the Setup or the portable archive; download the latest Setup.exe from the release page and run it. The release page is on GitHub.

A source ZIP with `.github/` or `tests/` is distinguished from the portable archive,
and a Windows `app/` missing its sibling `runtime/pythonw.exe` is refused. Git checkouts
retain their git-pull guidance. Synthetic tests prove no download or launch occurs for
these unsupported layouts; existing installer/portable tests remain passing.

## Standalone suite results

Every command in [commands.txt](reports/b661_h1/commands.txt) was run from this worktree
with plain `python3`, `PYTHONPATH=.`, `QT_QPA_PLATFORM=offscreen` and
`MOD_STUDIO_NO_UPDATE_CHECK=1`. The UI-budget test ran alone. Other test files used up
to two independent interpreters. Times below are unittest's own reported durations.

| Suite (`tests/mod_editor/`) | Tests | Output duration | Final result |
|---|---:|---:|---|
| `test_b661_workspace_qt.py` | 7 | 2.239 s | OK |
| `test_b661_kit_build.py` | 2 | 10.255 s | OK |
| `test_responsive_json.py` | 3 | 0.149 s | OK |
| `test_studio_inspection.py` | 2 | 0.298 s | OK |
| `test_self_update_manual_layout.py` | 1 | 0.002 s | OK |
| `test_2k5_stale_original_cache.py` | 10 | 0.020 s | OK |
| `test_2k5_build_parse_caches.py` | 14 | 0.365 s | OK |
| `test_studio_session.py` | 18 | 0.508 s | OK |
| `test_studio_facade.py` | 11 | 0.017 s | OK |
| `test_team_kit_bundle.py` | 7 | 8.516 s | OK |
| `test_uniform_bundle_cross_project.py` | 8 | 3.093 s | OK |
| `test_team_kit_product_integration.py` | 7 | 17.063 s | OK |
| `test_nfl2k5_equipment_texture_chain.py` | 16 | 3.924 s | OK |
| `test_nfl2k5_equipment_texture_native.py` | 5 | 0.245 s | OK |
| `test_nfl2k5_equipment_import.py` | 11 | 0.723 s | OK |
| `test_nfl2k5_equipment_import_wiring.py` | 6 | 0.594 s | OK |
| `test_nfl2k5_equipment_consumers.py` | 17 | 19.629 s | OK |
| `test_nfl2k5_uniform_catalog.py` | 5 | 1.290 s | OK |
| `test_nfl2k5_text_catalog.py` | 9 | 2.400 s | OK |
| `test_visual_decode_cache.py` | 3 | 0.002 s | OK |
| `test_2k5_visual_io_routing.py` | 4 | 0.115 s | OK |
| `test_startup_performance.py` | 8 | 1.463 s | OK |
| `test_mod_build_performance.py` | 6 | 6.695 s | OK |
| `test_studio_shell_layout_qt.py` | 18 | 34.322 s | OK |
| `test_beta66_1_adapter_imports.py` | 3 | 0.345 s | OK |
| `test_self_update.py` | 26 | 1.376 s | OK |
| `test_update_check.py` | 21 | 0.005 s | OK |
| `test_provider_integrity.py` | 7 | 8.391 s | OK |
| `test_providers.py` | 33 | 3.696 s | OK |
| `test_nfl2k5_extended_visuals.py` | 9 | 0.145 s | OK |
| `test_studio_visual_asset_routing.py` | 14 | 7.896 s | OK |
| `test_studio_qt_models.py` | 9 | 1.344 s | OK |
| `test_product_shell_accessibility_qt.py` | 6 | 60.605 s | OK |
| `test_scorebug_studio_panel_qt.py` | 11 | 7.111 s | OK |
| `test_2k5_uniform_equipment_export.py` | 16 | 29.616 s | OK (skipped=2) |

The two equipment-export skips are exact missing inputs: the optional reviewed
`reports/assets/nfl2k5_uniform_tset_textures.tsv` source table, and the separate private
retail composer fixture pair. Available retail equipment decode/roundtrip tests ran.
The previously unguarded missing TSV now uses `SkipTest`; compact catalog identity,
shape and contract checks still execute. The new H1 build and UI tests need no retail.

The first provider-integrity run correctly caught the stale expected closure counts.
The new `responsive_json.py` dependency changes unified/scorebug counts from 268/9 to
269/10. Exact closure-set equality, hashes, source checks and isolated namespace launch
all pass after updating those counts. No integrity assertion was removed.

```sh
python3 packaging/repin.py --apply
# applied 0 pin update(s)  [final run, after earlier pins were refreshed]
git diff --check
# no output; exit 0
```

## Protected integration, release limits and Noah's witness

Apply the top H1 section of [WIRING.md](WIRING.md), including all four allowlist paths,
and rerun repin after applying the GUI source blocks. The existing protected runtime
checker changes in this commit are mechanical pin refreshes only. The new required
closure entry is supplied as an exact insertion in WIRING. No registry row, preset,
XBE patch site or cave allocation changed.

The clean-release runtime gate is **not proved** in this unstaged worktree. The command
below was attempted and returned exit 1 because `reports/assets` is a symlink:

```sh
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 packaging/check_2k5_mod_studio_runtime.py
```

```text
2K5_MOD_STUDIO_RUNTIME_CLOSURE_REFUSED: reviewed target metadata directory is missing
```

Its exact log is [runtime-worktree.log](reports/b661_h1/runtime-worktree.log). Run the
allowlist/release/runtime gates against Claude's clean integrated stage; do not weaken
the symlink or provider checks. A full release staging/archive and full retail image
build were not attempted. `df -h /` showed **88G available**, already below the context's
100 GB floor for large writes. No retail payloads were copied into the repository or
reports. No emulator, display, audio playback, network, push or release was used.

**UNWITNESSED / required next witness:**

1. Claude applies WIRING, repins and gates the clean release, then runs the retail probe
   without `--pending-wiring`. This worktree's tests deliberately identify pending wiring.
2. Noah opens a disc in the Windows Setup/portable release and enters Uniforms first,
   with both a cold and warm project/catalog state. Confirm actual window responsiveness,
   first-page replacement and Retry. A fresh, never-indexed multi-GB extraction was not
   part of this read-only-cache replay.
3. Leave the Windows studio idle for two minutes and use Build, Scorebar and the other
   pages. The real network update check, Scorebar editing and every possible page/timer
   combination are outside the measured first-Uniforms idle scenario. If a hang recurs,
   relaunch with `MOD_STUDIO_STALL_LOG=1` and retain the diagnostic log.
4. Export a kit, make an obvious jersey and shoe edit, import it, verify preview/receipt,
   build a new disc and play that output. Coach's exact edited folder/project was not
   supplied. All in-game appearance and emulator behavior remain **UNWITNESSED**; synthetic
   decoded bytes prove the writer path, not gameplay rendering.
5. Confirm the recovery message in a manual Windows layout and that a supported Setup
   installation updates/reopens normally. No live update/download was attempted offline.

The report and evidence are a separate explicit-path documentation commit after the
implementation commit above. `git log -2 --oneline` identifies both.

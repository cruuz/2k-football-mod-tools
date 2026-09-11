# Beta 66 job C: APF UI report

Branch: `astra/b66-apf-ui`. Main implementation commit: `a45e7d54`. The final commit attempt could not write `/home/noah/2k-football-mod-tools/.git/worktrees/astra-hf63-digits/index.lock`: the Git metadata is mounted read-only. Final fixes and this report remain in the working tree and are also preserved as a follow-up commit in `.scratch/b66-final.bundle`, with a mail patch in `.scratch/b66-final-commit.patch`. The original branch therefore still points to `a45e7d54`. Nothing was pushed.

The owned UI work is complete. **133 APF suites pass in this working tree. The remaining installer suite passes in a private integration copy with the exact protected changes in [WIRING.md](WIRING.md).** The raw checkout intentionally retains the old protected endzone metadata pin and registry counts, so its installer gate still refuses the changed labels until that wiring lands. No protected checker, registry file, general release allowlist, or installer test was edited in the working tree.

## What changed

- One documented application theme in `mod_editor/apf_studio/apf_theme.py` covers pages, parentless and parented dialogs, tables, alternate rows, headers, combo popups, editors, tabs, indicators, groups, scrollbars, tooltips, menus, progress bars, splitters and dialog buttons. Status text, including disabled text, meets the 4.5:1 audit threshold. Game colors remain data.
- All 14 pages use compact headings and 36-pixel capability strips. Details retains complete cards, source findings, long guidance and research boundaries. Shared spacing, wrapping toolbars, bounded tabs, fixed preview canvases, empty-list Load actions and a fixed action footer replace the opening walls of cards. Audio batch tools and the Field Art editor/inventory/ownership map have separate tabs.
- Tables use readable alternating rows, elision and full-text hover tips. Natural header sorting moves visual rows without changing the logical indices used by writers or losing embedded mapping controls. Ctrl+F targets the visible search, Escape clears searches without erasing an authoring field, and Enter transfers focus into the inspector. Geometry, last page and workspace tabs persist alongside the existing recent-file and recovery state.
- PS3 mapping puts the reason staging is disabled above the table. Select all matched, Clear and Next free matching slot make variant collisions actionable. Dialogs fit the available screen; oversized bodies scroll while their button boxes stay visible.
- Team Art is the first Logos & Team Art workspace and is linked from Field Art and Uniforms. It exposes **538 packages**: 118 crests, 118 endzones, 206 wordmarks, and 24 each of jerseys, shoulders, pants and digits. Labels include entry and package identity. Filters cover writable, staged and proved retail-team uses. The inspector resolves dimensions, codec, semantic layers, inner indices and crest logocache index.
- Thumbnails decode in workers into a source-scoped, decoder-versioned private PNG cache. Visible rows and one following row load progressively; scrolling or filtering schedules further thumbnails. Unseen packages remain indexed without holding the application busy. Stale source results cannot repopulate a different game. Long team labels elide without hiding the entry/package lines. The fixed-width inspector preview scales proportionally to the available height, with a tested gap before the scrollable layer details.
- Replacement uses the existing family writers. Crests require separate l0/l1 PNGs for six color masks and update the linked cache; endzones require the layers that package owns; digits accept a subset after combined-budget preflight. Multi-layer staging and per-package Revert each form one Undo action, with rollback on preparation failure. The normal build retains mip, compression, allocation and decode-back checks.
- Added the six requested confirmed endzone identifications and the two explicitly tentative labels. New crest and wordmark maps contain only the 24 proved built-in retail selector assignments in each family. Unidentified packages retain entry numbers.
- Fixed the three-argument color/normal digit encoders: they preserve mip bytes when no mip regeneration ran. Normal build calls still regenerate mips. Corrected the old alpha.85 format-59 read-only wording and added the requested alpha.86 section with Noah, SOFTDRINKTV, Aszemple and davidhbui credited.
- Corrected `Stride_number_field` being caught by the generic uniform-number name match. The live Field Art ownership map now contains its expected 258 records instead of failing at 257. Fixed previews retain their requested widths.
- Styled widgets and deferred dialogs are destroyed while QApplication is alive. This fixes the teardown crash found by the replay. The new launcher test exercises a real Qt event loop and verifies clean exit. Standalone recovery fixtures now dispatch DeferredDelete rather than leaving hidden windows until interpreter teardown.

User and maintainer documentation: [Team Art and theme guide](docs/mod_editor/apf2k8_team_art_browser.md), [alpha.86 changelog](docs/mod_editor/apf2k8_mod_studio_changelog.md).

## Evidence and limits

**PROVED offline:** live package counts, exact source identity resolution, 24 retail label assignments per crest/wordmark family, all supported dimensions and writer identities, six-mask pairing, family dispatch, source fences, cache invalidation, worker decoding, rollback and Undo. A non-retail crest was staged with distinct masks, saved/reopened as a project, reverted/undone, and compiled through the existing builder into its package plus both linked cache entries (171 and 213), in memory. Both window sizes passed effective-palette and bounded-control audits with the retail game loaded. All existing page routes remain present.

**UNWITNESSED:** changed artwork in game, Team Select visual consumption, gameplay changes, Windows/macOS native window behavior and operating-system-native file chooser chrome. Qt file choosers are covered offscreen. The retail-use filter deliberately excludes unproved endzone selector assignments. Staging arbitrary PNGs does not promise that they fit the final compressed allocation; the build still checks that.

The new Team Art capability is rendered and tested, but its protected registry row and matching action binding await integration. WIRING includes the full row, exact insertion order, metadata hashes, runtime import closure, capability count updates and the protected installer assertion. Its complete public runtime/installer wiring was exercised in a private copy. The older optional packaging `--source` path has stale starting-branch inventory expectations; its observed values are recorded in WIRING, and no success is claimed for that separate gate.

No Xenia, emulator, audio playback, network request, push, or retail payload publication occurred. Retail source: `/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)`, read-only. No retail payload was added to the repository. Screenshots and derived previews stay in `/tmp/b66-apf-ui`. Root already had about 98 GiB free at the initial check, below the handoff's 100 GiB target; this job did not create a disc image.

Read: `ASTRA_CONTEXT.md`, triage rows 24/25/29/30, `GUI_ASSET_BROWSER_PROPOSAL.md.full.md`, `BETA64_FOLLOWUP.md.full.md`, `endzone_labels_additions.json`, and the three cited `view/2k8-bugs_*.png` images in the read-only Discord dump. The screenshots reproduce the reported white Playbooks tables, invisible Design Play buttons and unclear disabled PS3 staging before the changes.

## Standalone verification

The final ledger is [final-verification.json](/tmp/b66-apf-ui/final-verification.json): **134 passing suite results, 1,461 reported tests, 25 conditional skips**. It records the scope and log path for every file. 133 results use the working tree; the installer result uses the private integration copy. The full run was followed by 46 UI/recovery/product rechecks and focused reruns after subsequent fixes.

The skips include 19 tests gated on absent pinned uniform-allocation reports, one optional presentation-research parity check whose pinned font reports are absent, slow opt-in cases, and unavailable executable/probe inputs. They are not runtime witnesses. The retail inventory, thumbnail and new paired-staging tests ran against the available source. A previously pytest-only crest audit now has a unittest entry point, so plain Python actually executes its assertion.

Each suite runs in a separate Python process, equivalent to:

```bash
for suite in tests/mod_editor/test_apf*.py; do
  PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 python3 "$suite"
done
```

The actual runner invokes `python3 <one-file>` for each of the 134 matching paths, with three independent processes at a time. Runner: `/tmp/b66-apf-ui/run_tests.py`; full-run log: `/tmp/b66-apf-ui/test-progress-final.log`; recheck runner/log: `/tmp/b66-apf-ui/run_rechecks.py`, `/tmp/b66-apf-ui/recheck-progress.log`. Final corrected exits supersede the early metadata-pin and teardown failures in those historical logs. The installer rerun uses the integration copy described below.

| Focused command or gate | Final output | Log |
| --- | --- | --- |
| `python3 tests/mod_editor/test_apf_theme_layout_qt.py` | `Ran 8 tests … OK` | [theme](/tmp/b66-apf-ui/theme-final8.log) |
| `python3 tests/mod_editor/test_apf_team_art.py` | `Ran 10 tests … OK` | [packages](/tmp/b66-apf-ui/tests/test_apf_team_art.log) |
| `python3 tests/mod_editor/test_apf_team_art_qt.py` | `Ran 6 tests … OK` | [browser](/tmp/b66-apf-ui/team-art-qt-final6.log) |
| `python3 tests/mod_editor/test_apf_number_encode_defaults.py` | `Ran 1 test … OK` | [encoder defaults](/tmp/b66-apf-ui/tests/test_apf_number_encode_defaults.log) |
| `python3 tests/mod_editor/test_apf_workspace_recovery.py` | `Ran 20 tests … OK`, process exit 0 | [recovery](/tmp/b66-apf-ui/recovery-disposal.log) |
| `python3 tests/mod_editor/test_apf_retail_crest_channel_audit.py` | `Ran 1 test … OK` | [standalone crest audit](/tmp/b66-apf-ui/retail-crest-standalone.log) |
| `python3 tools/apf_gui_replay_offscreen.py --receipt /tmp/b66-apf-ui/gui-replay-final.json` | `APF_GUI_REPLAY_PASS`, no unexpected dialog errors or crashes, process exit 0 | [replay](/tmp/b66-apf-ui/gui-replay-final.log) |
| Private candidate `test_apf_studio_installer.py` | `Ran 16 tests … OK` | [installer](/tmp/b66-apf-ui/installer-wiring-complete.log) |
| Private candidate `test_apf_capability_action_parity.py` | `Ran 11 tests … OK` | [capability parity](/tmp/b66-apf-ui/capability-integration.log) |
| Registry candidate, canonical validation with file checks skipped | `games=3 surfaces=21 capabilities=143` | [registry](/tmp/b66-apf-ui/registry-integration.log) |
| `python3 packaging/repin.py --apply` | `applied 0 pin update(s)` | [repin](/tmp/b66-apf-ui/repin-final.log) |

The installer candidate is `/tmp/b66-apf-ui/integration`. Its protected edits are exactly those documented for the public gate in WIRING. The immutable installer assertion changes only 142 to 143 for the one added registry row. It ran with `PATH=/tmp/b66-apf-ui/runtime-env/bin:$PATH`, `PYTHONPATH=/tmp/b66-apf-ui/integration`, offscreen Qt and update checks disabled. That private environment uses the already installed authentic Capstone 5.0.7 and distro Qt/Pillow; no dependency was downloaded. Four missing ignored extract-xiso files were restored from the existing beta-65 stage, and the release gate checked their pins. One missing sanitized scorebug research JSON was restored only after matching its pinned size/hash. No protected assertion or checker was weakened.

`compileall` and `git diff --check` pass. `git diff cc0407b3 -- packaging/check_*.py packaging/release-allowlist.txt mod_editor/capabilities/registry* tests/mod_editor/test_apf_studio_installer.py` is empty in the working tree.

## Before and after screenshots

These are regenerated screenshots, not copies of Claude's captures. Before: 1440×900, 14 empty and 14 loaded pages. After: both 1440×900 and 1366×768, each with 14 empty pages, 14 loaded pages, 30 dialogs and seven Team Art family views. Dialogs use the offscreen screen's 800×600 available bounds, which also exercises small-screen fitting. Dialog fixtures use synthetic inputs; loaded pages use the retail source.

Capture command, repeated with the appropriate dimensions/output directory:

```bash
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 \
python3 tools/apf_ui_snapshots.py \
  --source 'extracted/All-Pro Football 2K8 (USA)' \
  --output /tmp/b66-apf-ui/after-1366 \
  --cache-root /tmp/b66-apf-ui/preview-cache \
  --width 1366 --height 768 --audit --team-art-families
```

Receipts: [1366×768](/tmp/b66-apf-ui/after-1366/receipt.json), [1440×900](/tmp/b66-apf-ui/after-1440/receipt.json). The before directory also retains its original dialog receipt; its pages are listed explicitly below because the baseline dialogs-only pass rewrote that receipt's page list.

| Page | Before empty | Before loaded | After empty (1440) | After loaded (1440) | After loaded (1366) |
| --- | --- | --- | --- | --- | --- |
| Getting Started | [PNG](/tmp/b66-apf-ui/before/empty/00-getting_started.png) | [PNG](/tmp/b66-apf-ui/before/loaded/00-getting_started.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/00-getting_started.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/00-getting_started.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/00-getting_started.png) |
| Uniforms | [PNG](/tmp/b66-apf-ui/before/empty/01-uniforms.png) | [PNG](/tmp/b66-apf-ui/before/loaded/01-uniforms.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/01-uniforms.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/01-uniforms.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/01-uniforms.png) |
| Rosters | [PNG](/tmp/b66-apf-ui/before/empty/02-rosters.png) | [PNG](/tmp/b66-apf-ui/before/loaded/02-rosters.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/02-rosters.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/02-rosters.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/02-rosters.png) |
| Team Identity | [PNG](/tmp/b66-apf-ui/before/empty/03-team_identity.png) | [PNG](/tmp/b66-apf-ui/before/loaded/03-team_identity.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/03-team_identity.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/03-team_identity.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/03-team_identity.png) |
| Logos | [PNG](/tmp/b66-apf-ui/before/empty/04-logos.png) | [PNG](/tmp/b66-apf-ui/before/loaded/04-logos.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/04-logos.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/04-logos.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/04-logos.png) |
| Scorebug | [PNG](/tmp/b66-apf-ui/before/empty/05-scorebug.png) | [PNG](/tmp/b66-apf-ui/before/loaded/05-scorebug.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/05-scorebug.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/05-scorebug.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/05-scorebug.png) |
| Field Art | [PNG](/tmp/b66-apf-ui/before/empty/06-field_art.png) | [PNG](/tmp/b66-apf-ui/before/loaded/06-field_art.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/06-field_art.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/06-field_art.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/06-field_art.png) |
| Stadiums | [PNG](/tmp/b66-apf-ui/before/empty/07-stadiums.png) | [PNG](/tmp/b66-apf-ui/before/loaded/07-stadiums.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/07-stadiums.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/07-stadiums.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/07-stadiums.png) |
| Menus | [PNG](/tmp/b66-apf-ui/before/empty/08-menus.png) | [PNG](/tmp/b66-apf-ui/before/loaded/08-menus.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/08-menus.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/08-menus.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/08-menus.png) |
| Audio | [PNG](/tmp/b66-apf-ui/before/empty/09-audio.png) | [PNG](/tmp/b66-apf-ui/before/loaded/09-audio.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/09-audio.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/09-audio.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/09-audio.png) |
| Gameplay | [PNG](/tmp/b66-apf-ui/before/empty/10-gameplay.png) | [PNG](/tmp/b66-apf-ui/before/loaded/10-gameplay.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/10-gameplay.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/10-gameplay.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/10-gameplay.png) |
| Playbooks | [PNG](/tmp/b66-apf-ui/before/empty/11-playbooks.png) | [PNG](/tmp/b66-apf-ui/before/loaded/11-playbooks.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/11-playbooks.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/11-playbooks.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/11-playbooks.png) |
| Franchise | [PNG](/tmp/b66-apf-ui/before/empty/12-franchise.png) | [PNG](/tmp/b66-apf-ui/before/loaded/12-franchise.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/12-franchise.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/12-franchise.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/12-franchise.png) |
| All Assets | [PNG](/tmp/b66-apf-ui/before/empty/13-all_assets.png) | [PNG](/tmp/b66-apf-ui/before/loaded/13-all_assets.png) | [PNG](/tmp/b66-apf-ui/after-1440/empty/13-all_assets.png) | [PNG](/tmp/b66-apf-ui/after-1440/loaded/13-all_assets.png) | [PNG](/tmp/b66-apf-ui/after-1366/loaded/13-all_assets.png) |

The matching 1366×768 empty pages use the same filenames under `/tmp/b66-apf-ui/after-1366/empty/`; all 14 paths are also in its receipt.

| Dialog | Before | After 1440 run | After 1366 run |
| --- | --- | --- | --- |
| Design Play | [PNG](/tmp/b66-apf-ui/before/dialogs/00-PlayDesignDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/00-PlayDesignDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/00-PlayDesignDialog.png) |
| Design Formation | [PNG](/tmp/b66-apf-ui/before/dialogs/01-FormationDesignDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/01-FormationDesignDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/01-FormationDesignDialog.png) |
| Add a CPU book call | [PNG](/tmp/b66-apf-ui/before/dialogs/02-CpuCallDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/02-CpuCallDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/02-CpuCallDialog.png) |
| Import PS3 bundle — assign teams | [PNG](/tmp/b66-apf-ui/before/dialogs/03-Ps3BundleMappingDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/03-Ps3BundleMappingDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/03-Ps3BundleMappingDialog.png) |
| Replace Entry 836 · entry 836 | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/04-TeamArtReplaceDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/04-TeamArtReplaceDialog.png) |
| Convert normal logo to APF color regions | [PNG](/tmp/b66-apf-ui/before/dialogs/04-NormalLogoRegionDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/05-NormalLogoRegionDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/05-NormalLogoRegionDialog.png) |
| Place full-shell helmet logo | [PNG](/tmp/b66-apf-ui/before/dialogs/05-HelmetLogoPlacementDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/06-HelmetLogoPlacementDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/06-HelmetLogoPlacementDialog.png) |
| Preview replacement | [PNG](/tmp/b66-apf-ui/before/dialogs/06-SlotImagePreviewDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/07-SlotImagePreviewDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/07-SlotImagePreviewDialog.png) |
| Review APF ratings-sheet import | [PNG](/tmp/b66-apf-ui/before/dialogs/07-RatingSheetImportPreviewDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/08-RatingSheetImportPreviewDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/08-RatingSheetImportPreviewDialog.png) |
| Configure external XMA1 encoder | [PNG](/tmp/b66-apf-ui/before/dialogs/08-ExternalXma1EncoderDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/09-ExternalXma1EncoderDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/09-ExternalXma1EncoderDialog.png) |
| Set up your XMA1 encoder | [PNG](/tmp/b66-apf-ui/before/dialogs/09-Xma1EncoderSetupWizard.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/10-Xma1EncoderSetupWizard.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/10-Xma1EncoderSetupWizard.png) |
| Affected roster fields | [PNG](/tmp/b66-apf-ui/before/dialogs/10-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/11-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/11-QDialog.png) |
| Formation and personnel | [PNG](/tmp/b66-apf-ui/before/dialogs/11-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/12-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/12-QDialog.png) |
| Getting Started · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/13-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/13-QDialog.png) |
| Uniforms & Equipment · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/14-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/14-QDialog.png) |
| Rosters & Players · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/15-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/15-QDialog.png) |
| Team Identity · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/16-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/16-QDialog.png) |
| Logos & Team Art · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/17-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/17-QDialog.png) |
| Scorebug & Presentation · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/18-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/18-QDialog.png) |
| Field Art · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/19-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/19-QDialog.png) |
| Stadium Studio · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/20-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/20-QDialog.png) |
| Menus & Text · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/21-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/21-QDialog.png) |
| Audio · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/22-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/22-QDialog.png) |
| Sliders & Gameplay · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/23-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/23-QDialog.png) |
| Playbooks & Plays · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/24-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/24-QDialog.png) |
| Season & Franchise Lab · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/25-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/25-QDialog.png) |
| All Game Assets · Details | New dialog | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/26-QDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/26-QDialog.png) |
| APF Mod Studio | [PNG](/tmp/b66-apf-ui/before/dialogs/12-QMessageBox.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/27-QMessageBox.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/27-QMessageBox.png) |
| Choose a PNG | [PNG](/tmp/b66-apf-ui/before/dialogs/13-QFileDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/28-QFileDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/28-QFileDialog.png) |
| Choose stock assignment | [PNG](/tmp/b66-apf-ui/before/dialogs/14-QInputDialog.png) | [PNG](/tmp/b66-apf-ui/after-1440/dialogs/29-QInputDialog.png) | [PNG](/tmp/b66-apf-ui/after-1366/dialogs/29-QInputDialog.png) |

The 14 Details dialogs and Team Art replacement dialog are new. Their previous information appeared inline on the before page screenshots.

| Team Art family | Packages | 1440×900 | 1366×768 |
| --- | --- | --- | --- |
| logo | 118 | [PNG](/tmp/b66-apf-ui/after-1440/team-art/logo.png) | [PNG](/tmp/b66-apf-ui/after-1366/team-art/logo.png) |
| endzone | 118 | [PNG](/tmp/b66-apf-ui/after-1440/team-art/endzone.png) | [PNG](/tmp/b66-apf-ui/after-1366/team-art/endzone.png) |
| textlogo | 206 | [PNG](/tmp/b66-apf-ui/after-1440/team-art/textlogo.png) | [PNG](/tmp/b66-apf-ui/after-1366/team-art/textlogo.png) |
| jersey | 24 | [PNG](/tmp/b66-apf-ui/after-1440/team-art/jersey.png) | [PNG](/tmp/b66-apf-ui/after-1366/team-art/jersey.png) |
| shoulder | 24 | [PNG](/tmp/b66-apf-ui/after-1440/team-art/shoulder.png) | [PNG](/tmp/b66-apf-ui/after-1366/team-art/shoulder.png) |
| pants | 24 | [PNG](/tmp/b66-apf-ui/after-1440/team-art/pants.png) | [PNG](/tmp/b66-apf-ui/after-1366/team-art/pants.png) |
| number | 24 | [PNG](/tmp/b66-apf-ui/after-1440/team-art/number.png) | [PNG](/tmp/b66-apf-ui/after-1366/team-art/number.png) |

## Noah's runtime witness

Load the integrated beta-66 release, browse a non-retail crest and a known retail team, replace distinct l0/l1 masks, save/reopen the project and build to a separate destination. Confirm the helmet and linked Team Select art in game. Repeat for a paired endzone, a rectangular wordmark and a digit set. Exercise Design Play, PS3 duplicate mapping, and dialogs on the target operating system. These are the remaining visual/runtime witnesses, not claims made by the offline results.

## Final commit handoff

The private Git directory `.scratch/b66-final.git` uses this same working tree and reads existing objects without changing the protected Git metadata. Its `astra/b66-apf-ui` branch contains the final commit on top of `a45e7d54`; the bundle contains that one new commit and requires the existing implementation commit. Inspect with `git bundle list-heads .scratch/b66-final.bundle`. A maintainer can apply `.scratch/b66-final-commit.patch` using `git am` in a clean checkout at `a45e7d54`.

For this existing working tree, the following explicit-path commit preserves the same changes once its Git metadata is writable. The command deliberately leaves the supplied context files, retail symlink and private evidence untracked:

```bash
git add -- ASTRA_REPORT.md WIRING.md mod_editor/apf_studio/gui.py mod_editor/apf_studio/team_art_qt.py mod_editor/apf_studio/ui_audit.py tests/mod_editor/test_apf_retail_crest_channel_audit.py tests/mod_editor/test_apf_team_art_qt.py tests/mod_editor/test_apf_theme_layout_qt.py tests/mod_editor/test_apf_workspace_recovery.py tools/apf_gui_replay_offscreen.py tools/apf_ui_snapshots.py
git commit --only -m 'fix(apf): finish viewport audits and deterministic Qt shutdown' -- ASTRA_REPORT.md WIRING.md mod_editor/apf_studio/gui.py mod_editor/apf_studio/team_art_qt.py mod_editor/apf_studio/ui_audit.py tests/mod_editor/test_apf_retail_crest_channel_audit.py tests/mod_editor/test_apf_team_art_qt.py tests/mod_editor/test_apf_theme_layout_qt.py tests/mod_editor/test_apf_workspace_recovery.py tools/apf_gui_replay_offscreen.py tools/apf_ui_snapshots.py
```

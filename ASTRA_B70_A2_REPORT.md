# Beta 70 A2: T3, APF-1 and T1 integration

## Result and evidence boundary

Integrated on `astra/b70-a2-integrate`, based on `local/stack-beta-70` at `8b4e3dbf`.
All required production wiring is applied. T1 section 1 (Windows helper/CI) and the checked-digit retry UI/writer contract remain out of scope. The optional section 2 digit measurement candidate was tested and reverted because the complete requested standalone gate could not be green with this checkout's missing private inputs.

**PROVED:** the recorded standalone executions, exact shared registry rows and counts, unchanged protected-file hashes, byte-producing regression goldens, actual completion consumers, executable form readback, offscreen state transitions, and staged APF release/runtime checks. **HYPOTHESIS:** explanations of the reporters' original game failures, audible improvement, coaching-scheme effects, and Windows/macOS performance beyond the measured host. **Every A2/T1/T3/APF-1 beta-70 in-game outcome is UNWITNESSED.** No emulator, display, listening session, network, push or message to a reporter was used. Historical reporter/Claude witnesses remain attributed to their original runs, not claimed as A2 verification.

Delivery uses writable private Git metadata at `/tmp/astra-b70-a2-git`. The first ordinary merge failed with `Read-only file system` when Git tried to create the shared worktree's `ORIG_HEAD.lock`. The shared branch still points to `8b4e3dbf`; the committed integration branch is in the portable bundle **`.scratch/astra-b70-a2-integrate.bundle`**. The checked-out worktree contains the delivered files. No shared Git metadata or other worktree was edited.

## Merges and preserved handoffs

Applied in the requested order:

1. `e64d61aa`, `astra/b70-t3-game-audio`, merged as `8086c0fe`. Copied the final T3 report and wiring to `ASTRA_B70_T3_REPORT.md` and `WIRING_B70_T3.md` in that merge. Fetched `/home/noah/2k-worktrees/astra-b70-t3/ASTRA_T3_HANDOFF.bundle` and cherry-picked its documentation commit `1c693ace` as `19b1b840`, preserving both changelog sides.
2. `665b1cb6`, `astra/b70-apf1`, merged as `0572d096`. Copied APF-1's final report and wiring to `ASTRA_B70_APF1_REPORT.md` and `WIRING_B70_APF1.md`. Its report identified an additional final bundle, `/home/noah/2k-worktrees/astra-b70-apf1/reports/b70_apf1-final.bundle`. Inspected and applied `71e1a802` as `371222ee`: the staged play-call preview had omitted replacement recipes, and the final change fixes that consumer, preserves strict MASTER parsing, and includes matching regression coverage/evidence. This is the extra APF integration seam fix beyond the requested checkpoint.
3. `09d1e687`, `refs/astra/b70-t1`, merged as `b35c0f86`, including `d208076c`, `5ec53965`, and `09d1e687` on `df9b9dcf`. Copied its report and wiring to `ASTRA_B70_T1_REPORT.md` and `WIRING_B70_T1.md`. Removed only surplus EOF blank lines from its two profile text logs so the merge passes the whitespace gate; golden bytes and measurements are unchanged.

Generic `ASTRA_REPORT.md`/`WIRING.md` add/add conflicts selected the incoming handoff only after preserving the preceding job-specific copy. This report replaces the generic report; `WIRING.md` retains T1's document for its snippet regression. Read preserved historical references to `WIRING.md` alongside that job's matching `WIRING_B70_*.md`.

Pin conflicts selected the integrated stack side and were regenerated with `python3 packaging/repin.py --apply`. Changelog conflicts retained all distinct changes under the existing beta-70 headings. APF's portable-policy correction was merged into its PS3 speed bullet. The new bullets quote Coach Edwards, X_Ray, Mud, Aszemple and Urianus, contain no em dashes, and have no duplicate change bullet.

Commits stage explicit paths. Git refuses path-limited porcelain merge commits, so merge commits were created from an index checked against the explicit path list, using `write-tree`/`commit-tree` with both parents. Ordinary commits use `git commit -- <explicit paths>`. No `git add -A` or push was used.

## Every wiring item and landing location

`packaging/repin.py --apply` regenerates SHA pins, not capability counts or missing dependency rows. Both 2K5 shared count pins are 173; its product count is 100. APF retains 72 capabilities. The uniform JSON is exactly the supplied object in canonical ID order, and the APF scheme row exactly matches APF-1's supplied replacement. The three Music rows retain runtime `not-tested` and all requested evidence/reason/scope/summary changes.

| Wiring item | Final file:line |
| --- | --- |
| T3 audio song forwarder | [mod_editor/core/audio_conform.py:301](mod_editor/core/audio_conform.py#L301) |
| T3 audio fixed-slot forwarder | [mod_editor/core/audio_conform.py:308](mod_editor/core/audio_conform.py#L308) |
| T3 2K5 audio allowlist | [packaging/release-allowlist.txt:672](packaging/release-allowlist.txt#L672) |
| T3 installed form, both readers | [mod_editor/core/nfl2k5_throw_tuning.py:693](mod_editor/core/nfl2k5_throw_tuning.py#L693), [mod_editor/core/nfl2k5_throw_tuning.py:822](mod_editor/core/nfl2k5_throw_tuning.py#L822) |
| T3 inspect form | [mod_editor/core/mod_build.py:589](mod_editor/core/mod_build.py#L589) |
| T3 preset defaults | [mod_editor/core/mod_build.py:342](mod_editor/core/mod_build.py#L342), [mod_editor/core/mod_build.py:363](mod_editor/core/mod_build.py#L363), [mod_editor/core/mod_build.py:385](mod_editor/core/mod_build.py#L385) |
| T3 Build caption/help | [mod_editor/gui/build_panel_qt.py:565](mod_editor/gui/build_panel_qt.py#L565) |
| T3 Build mode choices | [mod_editor/gui/build_panel_qt.py:573](mod_editor/gui/build_panel_qt.py#L573) |
| T3 Build installed form | [mod_editor/gui/build_panel_qt.py:1283](mod_editor/gui/build_panel_qt.py#L1283) |
| T3 Build refresh and saved-project seam | [mod_editor/gui/build_panel_qt.py:1766](mod_editor/gui/build_panel_qt.py#L1766) |
| T3 Gameplay PATCHES | [mod_editor/gui/gameplay_patches_panel_qt.py:152](mod_editor/gui/gameplay_patches_panel_qt.py#L152) |
| T3 Gameplay LABELS | [mod_editor/gui/gameplay_patches_panel_qt.py:318](mod_editor/gui/gameplay_patches_panel_qt.py#L318) |
| T3 Gameplay refresh/badge | [mod_editor/gui/gameplay_patches_panel_qt.py:847](mod_editor/gui/gameplay_patches_panel_qt.py#L847) |
| T3 Gameplay choice writer | [mod_editor/gui/gameplay_patches_panel_qt.py:340](mod_editor/gui/gameplay_patches_panel_qt.py#L340) |
| T3 uniform registry row | [mod_editor/capabilities/registry.v1.json:11722](mod_editor/capabilities/registry.v1.json#L11722) |
| T3 bank-rebuild evidence/reason/scope/summary | [mod_editor/capabilities/registry.v1.json:8886](mod_editor/capabilities/registry.v1.json#L8886) |
| T3 fixed-slot evidence/reason | [mod_editor/capabilities/registry.v1.json:8965](mod_editor/capabilities/registry.v1.json#L8965) |
| T3 playlist evidence/scope | [mod_editor/capabilities/registry.v1.json:9036](mod_editor/capabilities/registry.v1.json#L9036) |
| T3 shared 2K5 runtime count assertion | [packaging/check_2k5_mod_studio_runtime.py:2175](packaging/check_2k5_mod_studio_runtime.py#L2175) |
| T3 shared 2K5 runtime count banner | [packaging/check_2k5_mod_studio_runtime.py:2582](packaging/check_2k5_mod_studio_runtime.py#L2582) |
| T3 phase1 count pin | [tests/mod_editor/test_phase1_packaging.py:571](tests/mod_editor/test_phase1_packaging.py#L571) |
| T3 APF shared runtime count | [packaging/check_apf2k8_mod_studio_runtime.py:1355](packaging/check_apf2k8_mod_studio_runtime.py#L1355) |
| T3 APF installer count pin | [tests/mod_editor/test_apf_studio_installer.py:360](tests/mod_editor/test_apf_studio_installer.py#L360) |
| T3 individual capability document packaging | [packaging/release-allowlist.txt:907](packaging/release-allowlist.txt#L907) |
| APF1 replacement registry row | [mod_editor/capabilities/registry.v1.json:3536](mod_editor/capabilities/registry.v1.json#L3536) |
| APF1 guide and three image allowlist paths | [packaging/apf2k8-release-allowlist.txt:292](packaging/apf2k8-release-allowlist.txt#L292), [packaging/apf2k8-release-allowlist.txt:293](packaging/apf2k8-release-allowlist.txt#L293), [packaging/apf2k8-release-allowlist.txt:294](packaging/apf2k8-release-allowlist.txt#L294), [packaging/apf2k8-release-allowlist.txt:295](packaging/apf2k8-release-allowlist.txt#L295) |
| APF1 reviewed image pins and reviewed-path set | [packaging/check_apf2k8_mod_studio_release.py:80](packaging/check_apf2k8_mod_studio_release.py#L80), [packaging/check_apf2k8_mod_studio_release.py:88](packaging/check_apf2k8_mod_studio_release.py#L88), [packaging/check_apf2k8_mod_studio_release.py:843](packaging/check_apf2k8_mod_studio_release.py#L843), [packaging/check_apf2k8_mod_studio_release.py:915](packaging/check_apf2k8_mod_studio_release.py#L915) |
| APF1 image validator | [packaging/check_apf2k8_mod_studio_release.py:842](packaging/check_apf2k8_mod_studio_release.py#L842) |
| APF1 image audit arm | [packaging/check_apf2k8_mod_studio_release.py:915](packaging/check_apf2k8_mod_studio_release.py#L915) |
| APF1 runtime image pins | [packaging/check_apf2k8_mod_studio_runtime.py:584](packaging/check_apf2k8_mod_studio_runtime.py#L584) |
| APF1 runtime guide function | [packaging/check_apf2k8_mod_studio_runtime.py:586](packaging/check_apf2k8_mod_studio_runtime.py#L586) |
| APF1 runtime guide call after book-unlock check | [packaging/check_apf2k8_mod_studio_runtime.py:2682](packaging/check_apf2k8_mod_studio_runtime.py#L2682) |
| T1 section 0 shell success | [mod_editor/gui/studio_qt.py:8018](mod_editor/gui/studio_qt.py#L8018) |
| T1 section 0 Build completion | [mod_editor/core/build_feedback.py:51](mod_editor/core/build_feedback.py#L51) |
| T1 section 2 delivered summary retained | [tools/nfl2k5_visual_mod_project.py:2754](tools/nfl2k5_visual_mod_project.py#L2754) |
| APF shared audio closure seam | [packaging/apf2k8-release-allowlist.txt:102](packaging/apf2k8-release-allowlist.txt#L102) |
| Older shared count consumer | [tests/mod_editor/test_b68_a1_audit.py:41](tests/mod_editor/test_b68_a1_audit.py#L41) |
| Product catalog row/count consumer | [tests/mod_editor/test_product_catalog.py:76](tests/mod_editor/test_product_catalog.py#L76) |
| 2K5 changelog section | [docs/mod_editor/2k5_mod_studio_changelog.md:3](docs/mod_editor/2k5_mod_studio_changelog.md#L3) |
| APF changelog section | [docs/mod_editor/apf2k8_mod_studio_changelog.md:3](docs/mod_editor/apf2k8_mod_studio_changelog.md#L3) |
| Music converter provider dependency pin | [mod_editor/core/providers.py:632](mod_editor/core/providers.py#L632) |
| Existing stack MNF font dependency pin | [mod_editor/core/providers.py:696](mod_editor/core/providers.py#L696) |
| Music converter runtime dependency/import | [packaging/check_2k5_mod_studio_runtime.py:136](packaging/check_2k5_mod_studio_runtime.py#L136), [packaging/check_2k5_mod_studio_runtime.py:1911](packaging/check_2k5_mod_studio_runtime.py#L1911) |
| Exact provider closure count regression | [tests/mod_editor/test_provider_integrity.py:204](tests/mod_editor/test_provider_integrity.py#L204) |

### Seams fixed during integration

- **Installed jersey form after saved-project restoration:** the literal T3 `apply_state` wiring correctly showed `rule`, but the existing project restore subsequently changed its disabled combo to saved `choice`. The real offscreen regression reproduced that failure. `BuildPanel._refresh` now restores the installed combo with signals blocked and derives enablement from the source gate. A source switch resets the selector to choice while remaining off; a saved rule still restores on a retail source. Both forms are read from synthetic executable bytes through `read_xbe`, `mod_build.inspect`, and `read_image` with a synthetic archive extent. Foreign-source refusal remains visible. No new jersey game-code bytes were introduced.
- **APF shared audio dependency:** the first integrated APF runtime stage refused because the newly wired `audio_conform` forwarders import `nfl2k5_music_conform`, absent from APF's allowlist. Added that source module alongside shared audio; both staged gates now pass. No Windows helper or new binary was supplied.
- **Exact provider dependency closure:** `test_provider_integrity` found 282 imported modules but only 280 pins. Added the new Music converter and the stack's existing `nfl2k5_scorebug_mnf_font.py` dependency pins, with exact measured hashes. The latter missing pin predates A2; the scorebug font implementation was not edited. Updated the exact closure test count and included Music in the 2K5 required/runtime module lists. The full integrity suite passes.
- **Other current registry consumers:** updated the older `test_b68_a1_audit` shared/product pins and `test_product_catalog`'s explicit jersey ID, uniform category count and total/editable counts. Their full files pass. Gameplay's old generic `Retail`/`Patch` help assertion now checks the specified T3 form/screen/retail-rule/UNWITNESSED wording; the full test passes.
- **Completion paths:** both actual UI/feedback consumers use `summarize_kept_retail`. The A2 test executes the real shell success callback, rather than only substituting the handoff snippet, and checks concise deduplicated rows, preserved receipt dictionaries, legacy sentence-only rows and unmeasured outcomes.

### Conditional T1 digit block: reverted

Located the applicable encoder/project suites in `tools/test_nfl_tset_png_import*.py`, `tools/test_nfl2k5_visual_mod_project.py`, and the digit-sheet, bounded-palette, dimension and Coach-digit suites in `tests/mod_editor` (there are no matching `test_nfl2k5_digit_art*.py` files here). Ran the same eleven files before and after the **exact** `max_encoded_size + 512` insertion and the minimum-overflow/lower-bound receipt change. Eight files exited zero both times; three importer programs failed both times before reaching the relevant runtime fixture because `reports/assets` inputs are absent. Available synthetic checks showed no regression, but the complete green prerequisite was not met. Reverted both candidate files byte-for-byte to their before-candidate state and retained T1's delivered summary contract.

Thus current digit receipts still provide at most their delivered one-byte lower bound, or an unmeasured shortfall for historical records. No exact digit byte measurement or checked smaller visible-mark retry is claimed. Equipment's already measured suggestions remain available. No descriptor/canvas shrinkage, Windows helper/CI change or checked-digit retry UI/writer contract was added.

## Verification commands and results

All test files ran as standalone Python programs. Common prefix for **every test-file row below**:

```sh
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tools python3 <test-file>
```

The exact expanded command, exit code, elapsed time and full output path are in [final-results.json](reports/b70_a2/final-results.json). It selects the final full-file rerun after each fix; all initial failures remain in the original logs. Main matrix plus two additional registry consumers: **82 files, 78 exit zero, 4 pre-existing nonzero, 813 reported unittest cases**. Including nine additional distinct digit/importer programs: **91 distinct programs, 84 exit zero, 7 pre-existing nonzero**. A zero exit with skips is explicitly identified below and is not evidence for the skipped private/platform case.

| Test file (command suffix) | Final result | Full output |
| --- | --- | --- |
| `tests/apf_h7a_no_overlap_test.py` | Ran 4 tests in 18.068s; OK | [log](reports/b70_a2/standalone/tests__apf_h7a_no_overlap_test.py.log) |
| `tests/apf_h7a_optimal_is_bounded_test.py` | Ran 4 tests in 21.548s; OK | [log](reports/b70_a2/standalone/tests__apf_h7a_optimal_is_bounded_test.py.log) |
| `tests/mod_editor/test_2k5_bounded_vclz_palette.py` | Ran 7 tests in 3.179s; OK (skipped=2) | [log](reports/b70_a2/digit-before/tests__mod_editor__test_2k5_bounded_vclz_palette.py.log) |
| `tests/mod_editor/test_2k5_digit_dimensions_per_target.py` | Ran 10 tests in 0.005s; OK (skipped=8) | [log](reports/b70_a2/digit-before/tests__mod_editor__test_2k5_digit_dimensions_per_target.py.log) |
| `tests/mod_editor/test_2k5_uniform_equipment_export.py` | Ran 13 tests in 1.435s; FAILED (errors=6, skipped=2) | [log](reports/b70_a2/standalone/tests__mod_editor__test_2k5_uniform_equipment_export.py.log) |
| `tests/mod_editor/test_2k5_vclz_bounded_importers.py` | Ran 16 tests in 0.434s; OK | [log](reports/b70_a2/digit-before/tests__mod_editor__test_2k5_vclz_bounded_importers.py.log) |
| `tests/mod_editor/test_apf_all_crest_slots.py` | Ran 15 tests in 2.186s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_all_crest_slots.py.log) |
| `tests/mod_editor/test_apf_b661_book_content.py` | Ran 5 tests in 30.436s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b661_book_content.py.log) |
| `tests/mod_editor/test_apf_b67_writers.py` | Ran 6 tests in 0.248s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b67_writers.py.log) |
| `tests/mod_editor/test_apf_b69_build.py` | Ran 1 test in 33.665s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b69_build.py.log) |
| `tests/mod_editor/test_apf_b69_editor_qt.py` | Ran 4 tests in 100.730s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b69_editor_qt.py.log) |
| `tests/mod_editor/test_apf_b69_formation_calling.py` | Ran 2 tests in 0.113s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b69_formation_calling.py.log) |
| `tests/mod_editor/test_apf_b69_launch_patches.py` | Ran 5 tests in 0.250s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b69_launch_patches.py.log) |
| `tests/mod_editor/test_apf_b69_retirement_native.py` | Ran 3 tests in 164.140s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b69_retirement_native.py.log) |
| `tests/mod_editor/test_apf_b69_schemes.py` | Ran 5 tests in 50.774s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b69_schemes.py.log) |
| `tests/mod_editor/test_apf_b70_stock_recipes.py` | Ran 5 tests in 216.895s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_b70_stock_recipes.py.log) |
| `tests/mod_editor/test_apf_book_identity_qt.py` | Ran 5 tests in 0.043s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_book_identity_qt.py.log) |
| `tests/mod_editor/test_apf_book_unlock.py` | Ran 19 tests in 28.234s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_book_unlock.py.log) |
| `tests/mod_editor/test_apf_crest_budget_import.py` | Ran 12 tests in 1.003s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_crest_budget_import.py.log) |
| `tests/mod_editor/test_apf_crest_fit.py` | Ran 10 tests in 31.178s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_crest_fit.py.log) |
| `tests/mod_editor/test_apf_helmet_crest_design_product.py` | Ran 13 tests in 1.267s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_helmet_crest_design_product.py.log) |
| `tests/mod_editor/test_apf_helmet_logo_regions.py` | Ran 12 tests in 4.450s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_helmet_logo_regions.py.log) |
| `tests/mod_editor/test_apf_logo_patch.py` | Ran 18 tests in 17.740s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_logo_patch.py.log) |
| `tests/mod_editor/test_apf_logocache_patch.py` | Ran 14 tests in 48.980s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_logocache_patch.py.log) |
| `tests/mod_editor/test_apf_playcall_research_native.py` | Ran 22 tests in 120.136s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_playcall_research_native.py.log) |
| `tests/mod_editor/test_apf_playcalling_editor_build.py` | Ran 3 tests in 80.494s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_playcalling_editor_build.py.log) |
| `tests/mod_editor/test_apf_playcalling_editor_facade.py` | Ran 7 tests in 2.652s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_playcalling_editor_facade.py.log) |
| `tests/mod_editor/test_apf_playcalling_editor_patches.py` | Ran 3 tests in 0.201s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_playcalling_editor_patches.py.log) |
| `tests/mod_editor/test_apf_playcalling_editor_qt.py` | Ran 10 tests in 3.906s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_playcalling_editor_qt.py.log) |
| `tests/mod_editor/test_apf_ps3_speed.py` | Ran 15 tests in 4.502s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_ps3_speed.py.log) |
| `tests/mod_editor/test_apf_ps3_speed_packages.py` | Ran 6 tests in 10.435s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_ps3_speed_packages.py.log) |
| `tests/mod_editor/test_apf_ps3_texture_bundle.py` | Ran 28 tests in 31.227s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_ps3_texture_bundle.py.log) |
| `tests/mod_editor/test_apf_ps3_texture_bundle_qt.py` | Ran 4 tests in 0.189s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_ps3_texture_bundle_qt.py.log) |
| `tests/mod_editor/test_apf_public_docs_registry_current.py` | Ran 5 tests in 0.108s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_public_docs_registry_current.py.log) |
| `tests/mod_editor/test_apf_studio_core.py` | Ran 9 tests in 0.025s; OK (skipped=1) | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_studio_core.py.log) |
| `tests/mod_editor/test_apf_studio_installer.py` | Ran 16 tests in 0.118s; FAILED (errors=3) | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_studio_installer.py.log) |
| `tests/mod_editor/test_apf_studio_safety.py` | Ran 27 tests in 0.114s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_studio_safety.py.log) |
| `tests/mod_editor/test_apf_team_art.py` | Ran 10 tests in 15.601s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_team_art.py.log) |
| `tests/mod_editor/test_apf_team_art_qt.py` | Ran 6 tests in 0.182s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_team_art_qt.py.log) |
| `tests/mod_editor/test_apf_team_logo_gui.py` | Ran 23 tests in 1.591s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_team_logo_gui.py.log) |
| `tests/mod_editor/test_apf_wave_integration.py` | Ran 8 tests in 13.907s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_apf_wave_integration.py.log) |
| `tests/mod_editor/test_audio_conform.py` | Ran 17 tests in 0.880s; OK (skipped=1) | [log](reports/b70_a2/standalone/tests__mod_editor__test_audio_conform.py.log) |
| `tests/mod_editor/test_b66_coach_digits.py` | Ran 12 tests in 5.934s; OK (skipped=1) | [log](reports/b70_a2/standalone/tests__mod_editor__test_b66_coach_digits.py.log) |
| `tests/mod_editor/test_b68_a1_audit.py` | Ran 10 tests in 7.469s; OK | [log](reports/b70_a2/closure-final/tests__mod_editor__test_b68_a1_audit.py.log) |
| `tests/mod_editor/test_b68_t1_build.py` | Ran 6 tests in 5.661s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_b68_t1_build.py.log) |
| `tests/mod_editor/test_b69_j1_build.py` | Ran 5 tests in 3.396s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_b69_j1_build.py.log) |
| `tests/mod_editor/test_b69_j1_fit.py` | Ran 5 tests in 5.460s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_b69_j1_fit.py.log) |
| `tests/mod_editor/test_b69_j1_native.py` | Ran 1 test in 1.364s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_b69_j1_native.py.log) |
| `tests/mod_editor/test_b69_j1_wiring.py` | Ran 7 tests in 6.717s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_b69_j1_wiring.py.log) |
| `tests/mod_editor/test_b70_a2_wiring.py` | Ran 4 tests in 0.993s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_b70_a2_wiring.py.log) |
| `tests/mod_editor/test_b70_t1_build_speed.py` | Ran 10 tests in 17.343s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_b70_t1_build_speed.py.log) |
| `tests/mod_editor/test_b70_t1_diagnostics.py` | Ran 5 tests in 0.966s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_b70_t1_diagnostics.py.log) |
| `tests/mod_editor/test_beta45_honesty_freeze.py` | Ran 9 tests in 4.151s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_beta45_honesty_freeze.py.log) |
| `tests/mod_editor/test_build_panel_qt.py` | Ran 13 tests in 2.813s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_build_panel_qt.py.log) |
| `tests/mod_editor/test_gameplay_patches_panel_qt.py` | Ran 1 test in 0.665s; OK | [log](reports/b70_a2/gameplay-final/tests__mod_editor__test_gameplay_patches_panel_qt.py.log) |
| `tests/mod_editor/test_hotfix63_digit_budget.py` | Ran 5 tests in 0.024s; OK (skipped=3) | [log](reports/b70_a2/standalone/tests__mod_editor__test_hotfix63_digit_budget.py.log) |
| `tests/mod_editor/test_mod_build.py` | Ran 11 tests in 1.948s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_mod_build.py.log) |
| `tests/mod_editor/test_music_conform.py` | Ran 7 tests in 1.193s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_music_conform.py.log) |
| `tests/mod_editor/test_music_panel_qt.py` | Ran 9 tests in 2.308s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_music_panel_qt.py.log) |
| `tests/mod_editor/test_music_service.py` | Ran 10 tests in 3.016s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_music_service.py.log) |
| `tests/mod_editor/test_music_simple.py` | Ran 12 tests in 17.860s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_music_simple.py.log) |
| `tests/mod_editor/test_music_simple_qt.py` | Ran 9 tests in 4.230s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_music_simple_qt.py.log) |
| `tests/mod_editor/test_nfl2k5_build_service.py` | Ran 28 tests in 0.149s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_build_service.py.log) |
| `tests/mod_editor/test_nfl2k5_digit_sheet.py` | Ran 3 tests in 0.384s; OK | [log](reports/b70_a2/digit-before/tests__mod_editor__test_nfl2k5_digit_sheet.py.log) |
| `tests/mod_editor/test_nfl2k5_digit_sheet_quality.py` | Ran 13 tests in 7.209s; OK (skipped=1) | [log](reports/b70_a2/digit-before/tests__mod_editor__test_nfl2k5_digit_sheet_quality.py.log) |
| `tests/mod_editor/test_nfl2k5_equipment_consumers.py` | Ran 19 tests in 27.215s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_equipment_consumers.py.log) |
| `tests/mod_editor/test_nfl2k5_equipment_import.py` | Ran 13 tests in 2.269s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_equipment_import.py.log) |
| `tests/mod_editor/test_nfl2k5_equipment_import_wiring.py` | Ran 6 tests in 1.710s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_equipment_import_wiring.py.log) |
| `tests/mod_editor/test_nfl2k5_equipment_retail_roundtrip.py` | Ran 2 tests in 15.546s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_equipment_retail_roundtrip.py.log) |
| `tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py` | Ran 3 tests in 1.789s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_equipment_scope_wiring.py.log) |
| `tests/mod_editor/test_nfl2k5_equipment_texture_chain.py` | Ran 19 tests in 3.287s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_equipment_texture_chain.py.log) |
| `tests/mod_editor/test_nfl2k5_equipment_texture_native.py` | Ran 7 tests in 0.320s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_equipment_texture_native.py.log) |
| `tests/mod_editor/test_nfl2k5_music_conform_integration.py` | Ran 29 tests in 23.470s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_music_conform_integration.py.log) |
| `tests/mod_editor/test_nfl2k5_music_metadata.py` | Ran 7 tests in 23.440s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_music_metadata.py.log) |
| `tests/mod_editor/test_nfl2k5_music_playlist.py` | Ran 15 tests in 12.951s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_music_playlist.py.log) |
| `tests/mod_editor/test_nfl2k5_music_playlist_library.py` | Ran 7 tests in 19.276s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_music_playlist_library.py.log) |
| `tests/mod_editor/test_nfl2k5_music_playlist_manifest.py` | Ran 2 tests in 4.129s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_music_playlist_manifest.py.log) |
| `tests/mod_editor/test_nfl2k5_music_queue.py` | Ran 3 tests in 3.803s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_music_queue.py.log) |
| `tests/mod_editor/test_nfl2k5_music_resample.py` | Ran 4 tests in 1.653s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_music_resample.py.log) |
| `tests/mod_editor/test_nfl2k5_uniform_choice.py` | Ran 18 tests in 8.289s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_uniform_choice.py.log) |
| `tests/mod_editor/test_nfl2k5_uniform_choice_screens.py` | Ran 2 tests in 0.440s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_nfl2k5_uniform_choice_screens.py.log) |
| `tests/mod_editor/test_phase1_packaging.py` | Ran 23 tests in 0.104s; FAILED (errors=1) | [log](reports/b70_a2/closure-final/tests__mod_editor__test_phase1_packaging.py.log) |
| `tests/mod_editor/test_product_catalog.py` | Ran 9 tests in 0.044s; OK | [log](reports/b70_a2/registry-consumers-final/tests__mod_editor__test_product_catalog.py.log) |
| `tests/mod_editor/test_project_document_workflow.py` | Ran 13 tests in 1.447s; FAILED (errors=6) | [log](reports/b70_a2/standalone/tests__mod_editor__test_project_document_workflow.py.log) |
| `tests/mod_editor/test_provider_integrity.py` | Ran 7 tests in 10.371s; OK | [log](reports/b70_a2/closure-final/tests__mod_editor__test_provider_integrity.py.log) |
| `tests/mod_editor/test_studio_facade.py` | Ran 11 tests in 0.024s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_studio_facade.py.log) |
| `tests/mod_editor/test_update_check.py` | Ran 21 tests in 0.004s; OK | [log](reports/b70_a2/standalone/tests__mod_editor__test_update_check.py.log) |
| `tools/test_nfl2k5_visual_mod_project.py` | Ran 46 tests in 2.312s; OK (skipped=10) | [log](reports/b70_a2/digit-before/tools__test_nfl2k5_visual_mod_project.py.log) |
| `tools/test_nfl_tset_png_import.py` | exit 1 (see missing-input traceback) | [log](reports/b70_a2/digit-before/tools__test_nfl_tset_png_import.py.log) |
| `tools/test_nfl_tset_png_import_dynamic_workflow.py` | exit 1 (see missing-input traceback) | [log](reports/b70_a2/digit-before/tools__test_nfl_tset_png_import_dynamic_workflow.py.log) |
| `tools/test_nfl_tset_png_import_xiso_direct_patch.py` | exit 1 (see missing-input traceback) | [log](reports/b70_a2/digit-before/tools__test_nfl_tset_png_import_xiso_direct_patch.py.log) |

### Release/runtime and structural gates

| Command/scope | Result |
| --- | --- |
| `python3 packaging/check_apf2k8_mod_studio_release.py` | Exit 2: existing CLI requires `release_root`; exact requested command recorded. |
| `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 packaging/check_apf2k8_mod_studio_runtime.py` in this worktree | Exit 1: existing public-stage guard refuses `extracted/`. |
| `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 <stage>/packaging/check_apf2k8_mod_studio_release.py <stage>` | **PASS**, 279 files, 10,273,870 bytes; reviewed editor image pins all pass. |
| `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 <stage>/packaging/check_apf2k8_mod_studio_runtime.py` | **PASS**, 156 modules, 72 APF capabilities; new `_check_book_identity_guide` executed after `_check_book_unlock_contract`. |
| `python3 -m mod_editor.capabilities.validate_registry --skip-file-checks` | **PASS**, schema v1, 3 games, 21 surfaces, 173 capabilities. |
| `python3 packaging/repin.py --apply` | Applied after source changes and last before writer commits; final run has no outstanding updates. |
| `git diff --check` and private Git staged whitespace check | **PASS**. |
| Protected files compared with `8b4e3dbf` | **PASS**, 128 files byte-identical; see [protected-files.json](reports/b70_a2/protected-files.json). |

The APF stage copied exact allowlisted worktree files. Four existing vendor files missing from the checkout were hydrated **only into a temporary stage** from the read-only alpha.69 release: the two reviewed extract-xiso executables and their two text files. Current release/runtime pins checked them. No gate was relaxed and no binary was committed. [APF stage receipt](reports/b70_a2/gates/apf-stage.json) records source paths, sizes, hashes, commands and outputs; every stage was removed.

The standalone APF installer file was additionally run in that hydrated source stage. It reached two otherwise masked subprocess failures: its `PYTHONNOUSERSITE=1` environment cannot import the machine's user-site `capstone`. `PYTHONNOUSERSITE=1 python3 -c 'import capstone'` reproduces this independently. This additional run is not marked passing. Direct APF runtime gates use the normal installed dependency environment and pass.

### Pre-existing reds and scope limits

| Program(s) | Existing cause, with failing location |
| --- | --- |
| `test_2k5_uniform_equipment_export.py` (6 errors, 2 skips) and `test_project_document_workflow.py` (6 errors) | Missing private `reports/assets` and `nfl2k5_player_portrait_compatibility.json`. Eager shell setup reaches `studio_qt._filter_unif_color_sets` then `nfl2k5_uniform_catalog.py:570`; catalog loading fails before the changed import/open/summary path. T1 already recorded these failures. |
| `test_phase1_packaging.py` (1 error) | Its unchanged reviewed-metadata read at line 374 cannot find `reports/assets/menu_state_trace.json`; this private input is absent from the baseline checkout. Count assertions pass. |
| `test_apf_studio_installer.py` (3 errors in the worktree) | `_stage_release`, line 41, cannot copy `tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md`; all four vendor files were absent before A2. Hydrating a temporary source stage gets past this and exposes the separate system/user-site `capstone` issue above. |
| `tools/test_nfl_tset_png_import.py` | Line 159 reads absent `reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.json`; same result before/after the optional candidate. |
| `tools/test_nfl_tset_png_import_dynamic_workflow.py` | `tools/nfl_tset_png_import.py:1038` reaches `import_png:795`, which reads absent `reports/assets/nfl2k5_resource_chunks_v2.json`; same before/after. |
| `tools/test_nfl_tset_png_import_xiso_direct_patch.py` | Line 35 reads absent `reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.tset.bin`; same before/after. |

No private catalog was fabricated and no failing test was converted into a pass or skip. The full registry file check was deliberately not run, per the brief; Claude owns that check on the hydrated stack. T3's known baseline missing `docs/research/apf_audio.md` remains a full-file-check prerequisite.

The combined cave manifest also remains Claude's regeneration follow-up from the shared context. The existing supported generator, `tools/nfl2k5_cave_oracle.py manifest`, requires a disposable 6+ GB disc image and a writable work directory; this job cannot write the designated external storage directory and did not make that disc copy on root. No manifest spans or fingerprints were manually stamped as proved. A2 changes inspection/defaults and archive/audio/editor wiring, not new XBE write sites or allocations; uniform owner changes remain documentation only. The conditional XBE write/cave/pairwise gates for changed executable bytes were not triggered by A2. Regenerate the combined stack manifest with the hydrated release gate before publishing.

The mandatory `test_apf_logo_patch.py` source-preservation regression creates and removes a temporary retail `0A` volume copy; it passed its source hash checks. This is transient test scratch, not a delivered game image or fixture. No complete disc build was performed. Other tests use synthetic files or read-only retail inputs with precise existing skips when absent. All temporary APF stages were removed; the delivered report/logs/bundle contain no retail payloads.

## Witnesses still required

- **X_Ray:** “I can't pick away jerseys at home and vice versa.” Use the preserved T3 recipe on Controller Assign and exhibition Team Select, with receipt showing **choice**; inspect actual field kits. Bounded handlers and kit letters do not prove the complete game transition. **rule** is fixed home dark/away white, not a colour picker. Practice/Xbox Live and era-only preview art remain outside that choice feature.
- **Mud:** “Audio imports to its own playlist and doesn't crash the game when loading from The Crib but audio sound bad.” His positive beta-69 Crib/import witness stays attributed. Compare a prepared encoded preview against My songs/The Crib; identify hiss, distortion, speed, channels or stutter. The new filter/dither test is numerical evidence, not listening evidence. Record add-button actions before attributing five repeated NOW PLAYING labels to automatic duplication.
- **Coach Edwards:** “it had been 67 minutes” refers to the photographed equipment import; “took 89 mins” remains a separate build report. Time his own import, repeat import and reopened project on Windows; verify retained-art messages and field appearance. A2 reran T1's six beta-69 span goldens and helper-disabled import/open tests, not his unavailable workload. Sock distortion is not claimed fixed here.
- **Aszemple/Urianus:** witness stock/independent book loading, situational play calls, edited personnel and rendered six-mask crests. APF-1's walkthrough and preserved report carry the exact four match checks. Urianus's “Not yet, got caught up with RL stuff” is pending playtesting, not a failed beta-70 test. No DM was sent.

## Delivery

- Current report: `ASTRA_REPORT.md`.
- Preserved sources: `ASTRA_B70_{T3,APF1,T1}_REPORT.md`, `WIRING_B70_{T3,APF1,T1}.md`.
- Verification receipts: `reports/b70_a2/`; commands and limitations also in `reports/b70_a2/REPRODUCE.md`.
- Portable commits: `.scratch/astra-b70-a2-integrate.bundle`, branch `astra/b70-a2-integrate`, prerequisite stack `8b4e3dbf` and its ancestors. Fetch in a writable integration checkout; inspect the bundle branch and merge as appropriate. No push.

```sh
git bundle verify /home/noah/2k-worktrees/astra-b70-a2/.scratch/astra-b70-a2-integrate.bundle
git fetch /home/noah/2k-worktrees/astra-b70-a2/.scratch/astra-b70-a2-integrate.bundle astra/b70-a2-integrate
```

ASTRA_DONE

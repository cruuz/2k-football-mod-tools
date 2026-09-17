# Beta 71.1 APF-7: Field opacity and formation fine-tuning

Branch `astra/b71-apf7-overlay-books`, based on release HEAD
`02bbadd184e85498a441d3be71e70f8de94b9b0a`. All commits use explicit paths
and the private git directory `.scratch/git`. The supplied worktree git metadata
is unchanged. Delivery: `.scratch/astra-b71-apf7.bundle`; final commit IDs, bundle
hash and verification are in `.scratch/astra-b71-apf7-delivery.json`.
No push, network, emulator, desktop display or audio was used. Qt ran offscreen.

## Facts and changes

**PROVED offline: the opacity failure is layout compression.** The release
`FieldMaterialOpacityPanel` puts eleven row layouts directly in a vertical
layout with no scroll viewport or row minimum. Its parent gives the remaining
space to the art workspace and opacity panel. Replaying the actual themed shell
at 1280×720 gives checkbox labels zero height; at 1920×1080 they have only
12–13 pixels while their 34-pixel spin boxes overlap. The screenshots reproduce
the failure with synthetic percentages, without loading or copying game art.

`mod_editor/apf_studio/field_material_qt.py:23` now supplies a resizable scroll
viewport, a 160-pixel minimum, and 32-pixel minimum controls. Values remain
percentages with two decimals. `mod_editor/apf_studio/gui.py:7850` gives the art
editor its own scrolling surface, and `:7861` places **Field overlay opacity**
in a full-height Field Art tab. This avoids making the two surfaces compete for
half the window. `:7938` and the All Field Art table retain readable list minima.
The named asset handoff selects the new editor container at `:8200`.

| Layout measurement | 1280×720 before | 1280×720 after | 1920×1080 before | 1920×1080 after |
| --- | ---: | ---: | ---: | ---: |
| Material label height | 0 px | 32 px | 12–13 px | 32 px |
| Percentage control height | 34 px, overlapping | 34 px | 34 px, overlapping | 34 px |
| Opacity list viewport | absent | 191 px | absent | 551 px |

The final list scrolls through all eleven rows at 720p and shows all rows at
1080p. Stage and Revert remain reachable. The same two-size test checks sibling
ownership and inventory tables, text/value bounds, the last row, and navigation
back to a writable art target.

**PROVED offline: “Give every team its own book” covers 24 disc teams per side,
48 independent resources across both sides.** It does not promise 36 teams.
`mod_editor/core/apf2k8_book_clone.py:184` explicitly documents the 24-team scope;
`:195` selects `teams[:24]`, and `:196` excludes labels still read by saved-team
slots. This code was already present in the APF-2 commit `7d954937`, and the
beta-67 P3 report documents 24 offensive plus 24 defensive copies at
`ASTRA_B67_P3_REPORT.md:60`. APF-6 did not reduce the allocator to 24.

The read-only retail census in `reports/b71_apf7/book-census.json` finds 40 roster
slots, 36 offensive labels and 33 defensive labels. The offensive labels resolve
to seven stock types plus USER-o; the defensive labels resolve to four stock
types plus USER-d. All sixteen slots 24–39 use label 25 on offense and 56 on
defense, pointing to USER-o and USER-d. These labels are not independent book
resources on the release source. The ordinary named-resource catalog includes
the two global special supplements as well. The count 36 matches the offensive
label table, not the number of disc teams or a 24-resource archive ceiling.

The legacy Book Identity utility lists all 40 serialized slots
(`mod_editor/apf_studio/book_identity_qt.py:339`) and filters unused same-side
labels (`:261`). Its low-level `CloneRequest` accepts team indices 0–39
(`mod_editor/core/apf2k8_book_clone.py:58`). This broader manual utility is distinct
from the automatic disc-team plan. Consolidation happened in APF-2, whose report
at `7d954937:ASTRA_REPORT.md` describes the Book Identity pointer; APF-6 retained
that workflow. There is no evidence of an earlier all-team action producing 36
independently assigned disc teams. **There was a loss of manual UI access:** the
consolidated page hid the legacy utility's broader allocation to saved slots.
This hotfix restores it through **Manual book allocation…** in CPU Play Calling
(`mod_editor/apf_studio/playcalling_editor_qt.py:144`). The shell handoff at
`gui.py:19462` opens Book Identity and expands its existing built-folder utility
(`book_identity_qt.py:169`). This offers all 40 slots and unused same-side labels;
the original review/build checks still apply. Build current staged edits first,
choose that built folder, review the allocation, and build a new folder. Opening
the utility stages nothing and does not automatically select or mutate a source.

The automatic allocator and saved-team readers are preserved, and the page
explains both scopes at `mod_editor/apf_studio/playcalling_service.py:45`. Saved
roster files have their separate Save Assignments workflow. Thus broader manual
access is restored without silently changing the 24-disc-team action to touch
saved-team slots, or claiming 36 automatic disc-team clones.

**Additional capacity proof:** the release roster has 28 initially unused labels
on each side (`reports/b71_apf7/legacy-label-census.json`). Two separate real,
read-only `compile_unlock` calls using all non-USER labels succeed with **35
offensive clones plus shared USER-o (36 assigned types)** and **32 defensive
clones plus shared USER-d (33 assigned types)**. These deliberately reassign 11
and 8 saved-team slots respectively; they are not the automatic plan and are not
a claim of one simultaneous 67-clone layout. Receipts and the unchanged reserved
label IDs are in `reports/b71_apf7/per-side-label-capacity.json`. The first combined
experiment correctly refused duplicate offense/defense resource names. This
explains both the larger historical label count and why changing the automatic
action's number would also change which saved-team slots it touches. Runtime
save loading can override these disc assignments and remains UNWITNESSED.

**PROVED offline: formation fine-tuning is beside the situation table and uses
the existing Confirm/queue transaction.** On the release tree, the three rating
sliders still existed at `playcalling_editor_qt.py:249` but were far below the
situation table, behind the live-mask and call-preview sections. The table itself
was read-only. The new `Fine-tune formation weights` group at
`mod_editor/apf_studio/playcalling_editor_qt.py:192` places formation selection,
all three ratings, Confirm and a draft preview beside the candidates. Headers
wrap, all weight columns fit, and picker/candidate selection stays aligned.

The draft preview at `mod_editor/apf_studio/playcalling_service.py:899` obtains
current staged state, applies pending requests and the draft rating through the
existing writers on copied state, and computes before/after candidates for every
situation. It never stores a recipe or Undo entry. The facade serializes it with
the existing session lock (`mod_editor/apf_studio/facade.py:193`). Confirm still
enters `PlayCallingService.confirm` at `playcalling_service.py:701`, including
automatic review, combined dependencies, coverage checks, clean-set staging,
inline blockers and one Undo step. Pending requests capture the original book,
formation and rating values even after browsing another book.

**Exact scope of “per situation”:** this restores and exposes the earlier three
short/medium/long raw ratings, with each situation's resulting personnel and
formation weights previewed before Confirm. `mod_editor/core/apf2k8_playcall_model.py:197`
reads three 3-bit ratings; `:208` interpolates them using down and distance.
Category weights average the relevant formation contributions at `:234`.
The 23 preview labels do not store 23 independent rating vectors, and the two
weight columns are not independently writable probabilities. Changes can affect
several situations. The page and guide state this explicitly. Independent numeric
overrides for each live bucket are not added or claimed. The existing APF-4
12-bucket exclusion mask and its runtime contract are unchanged.

## Screenshots and focused proof

| Evidence | 1280×720 | 1920×1080 |
| --- | --- | --- |
| Release opacity failure | [before](reports/b71_apf7/field-before-1280x720.png) | [before](reports/b71_apf7/field-before-1920x1080.png) |
| Fixed opacity tab | [after](reports/b71_apf7/field-after-1280x720.png) | [after](reports/b71_apf7/field-after-1920x1080.png) |
| Formation controls | [controls](reports/b71_apf7/cpu-weights-1280x720.png) | [controls](reports/b71_apf7/cpu-weights-1920x1080.png) |
| Draft situational weights | [preview](reports/b71_apf7/cpu-preview-1280x720.png) | [preview](reports/b71_apf7/cpu-preview-1920x1080.png) |
| Book capacity and manual handoff | [books](reports/b71_apf7/cpu-books-1280x720.png) | [books](reports/b71_apf7/cpu-books-1920x1080.png) |
| Restored 40-slot manual utility | [manual](reports/b71_apf7/manual-books-1280x720.png) | [manual](reports/b71_apf7/manual-books-1920x1080.png) |

Sibling Field Art Editor, Ownership Map and All Field Art captures are retained
as `art-*`, `ownership-*` and `inventory-*` images at both sizes, before and after.
The sibling list captures contain clearly synthetic rows and suppress their
no-source empty guidance so row geometry can be inspected. No production behavior
is bypassed in the layout assertions. The baseline script reloads only the two exact release UI modules from `02bbadd1`
in its own process; it does not switch or edit the worktree.

The Field captures use the real application shell/theme with clearly labeled
synthetic values and no game artwork. The CPU captures use the real service and
owned index read-only: O-ManBlock, formation 9, ratings 1/2/7, 23 preview rows,
zero staged modifications. Scripts, geometry JSON and command logs accompany
the images; these are Qt screenshots, not mockups or game screenshots.
The manual utility captures select slot 39 and show 28 unused offensive labels;
they perform no review compilation or game-folder build.

- `tests/mod_editor/test_apf_b711_overlay_books_qt.py:28`: both shell sizes,
  nonoverlapping labels and values, growing viewport, all rows reachable,
  sibling lists and art navigation.
- The same file at `:98`, `:125`, `:148`, `:156`: selected formation, draft preview
  with no project write, automatic Confirm reviews, bulk edits across named books,
  one Undo step, save/reopen, blockers, and both all-team buttons.
- `tests/mod_editor/test_apf_b711_weight_preview.py:24`: real synthetic SPLB writer
  and CPU model, different weights across situations, exact preview-versus-Confirm
  results across all 23 queries, pending state, input refusal, no draft mutation.
- `tests/mod_editor/test_apf_b711_book_scope.py:14`: real allocator on synthetic
  and retail ROST, 24 teams per side, 48 unique names, exact preservation of all
  sixteen saved-team assignments and their labels. Its third test compiles the
  broader per-side manual allocations against the real archive. The existing complete clone
  suite also compiles 48 retail clones against the actual archive directory.
- `tests/mod_editor/test_apf_book_identity_qt.py:120`: expanding the consolidated
  manual utility, loading all 40 slots, selecting slot 39, preserving unused-label
  filtering, and entering the existing review/build path. The full-shell test
  above also verifies the CPU-to-manual handoff.

The supplied context and release triage, APF-1 Book Identity, APF-4 and APF-6
reports were read. The beta-71 APF-2 report is not present under that name in the
root, so its report was read from commit `7d954937`; the older root APF-2 report
was also inspected. The two requested source screenshots were absent from this
worktree's evidence directory; the exact named files were inspected read-only in
the supplied hub's `beta71_evidence/`. They were not copied into the release.

## Boundaries and delivery

**UNWITNESSED:** every in-game result, mode-specific USER/save lifecycle, actual
loaded clone choice, field opacity in a match, and Windows/macOS rendering.
Native tests are bounded offline execution, not a played game. A gameplay retest
should compare the built named book, source/saved override, several situations
and the actual on-field result. No emulator was opened.

No executable patch, clone allocator, native weight formula, preset default or
capability row changed. The registry remains 176 total / 73 APF. All changed
runtime files were already allowlisted. Protected 2K5 code and shared git metadata
were not edited. `tools/apf_h7a_optimal` remains 0755. Retail inputs are read-only;
no retail fixture, disc or payload is committed. Existing suite-owned temporary
copies are removed by their tests. Exact local extractor dependencies were
verified from the archived public build with the existing hash pins; no download.
The private interpreter supplies the installed pinned Capstone 5.0.7 for isolated
packaging tests. Scratch remains under 200 MB.

Early failed experiments remain in the ledger: the baseline screenshot harness
initially mistook QWidget's `scroll` method for a viewport; the first invalid-input
test expected ValueError instead of the product's ValidationError. Both were
corrected and their complete final commands passed. The first attempted whole
Field workspace scroll layout was replaced by the final full-height opacity tab
after visual inspection. Later inspection caught and fixed the art handoff target
and aligned candidate selection. No failed final check is replaced with a passing
subtest or a skip-file validator.
The new manual-utility test initially omitted `book_identity` in its mocked review
receipt; its fixture was corrected and the whole file passed.
The first final-report aggregation mistook a commit's last explicit test path for
a test command. Its command filter now requires a Python interpreter before the
suite path; the complete test results themselves were unchanged.

## Validation and command ledger

**199/199 complete standalone suite files pass; 1885 reported tests, 11 explicit skips.** The full latest-complete matrix, including skips, is [suite_results.json](reports/b71_apf7/suite_results.json). Skipped cases do not constitute proof.

Provider integrity, product catalog, phase1 packaging, strict registry validation and `repin.py --apply` pass. Repin reports zero pin changes. The separately staged release passes both release and runtime gates: 289 files, 161 modules, 73 APF capabilities; no private, retail, symlink or undeclared payload.

All APF files in `tests/mod_editor/test_apf*.py`, the additional play-calling suite, the two studio Qt files and the requested gates run standalone with `PYTHONPATH=<worktree> QT_QPA_PLATFORM=offscreen`. Native files use the owned inputs and locally installed dependencies. Concurrent suite wall times reflect this host.

The 11 skips include optional pinned flat-PE/TU paths, the separately configured
book-unlock retail fixture, slow opt-in art cases, and an optional local emulator
source checkout. No new APF-7 test skipped. The owned archive allocation and the
actual native suites that completed are separately recorded; absent optional
fixtures are not claimed as native or runtime proof.

The complete commands, UTC starts, elapsed seconds, exit codes and full acceptance
output are in [commands.jsonl](reports/b71_apf7/commands.jsonl) and linked logs.
[inspection-commands.json](reports/b71_apf7/inspection-commands.json) also records
tool-side inspection/edit commands and their observed tool timing. Initial
bootstrap inspections predated the persistent recorder; their commands and
observed exit/durations are identified separately, without invented UTC starts.
Final report commit/bundle operations are logged in the external delivery receipt
to avoid claiming that a commit contains its own hash or timing.

| UTC start | Seconds | Exit | Command | Full log |
| --- | ---: | ---: | --- | --- |
| 2026-09-16T23:26:36.006979+00:00 | 0.263 | 0 | `python3 reports/b71_apf3/prepare_test_python.py` | [prepare-python.log](reports/b71_apf7/prepare-python.log) |
| 2026-09-16T23:26:36.630255+00:00 | 5.002 | 1 | `python3 reports/b71_apf7/screenshots.py before` | [screenshots-before.log](reports/b71_apf7/screenshots-before.log) |
| 2026-09-16T23:27:16.542982+00:00 | 4.239 | 0 | `python3 reports/b71_apf7/screenshots.py before` | [screenshots-before-2.log](reports/b71_apf7/screenshots-before-2.log) |
| 2026-09-16T23:27:56.721320+00:00 | 2.434 | 0 | `python3 -` | [book-census.log](reports/b71_apf7/book-census.log) |
| 2026-09-16T23:27:58.363785+00:00 | 4.33 | 0 | `python3 reports/b71_apf7/screenshots.py after` | [screenshots-after.log](reports/b71_apf7/screenshots-after.log) |
| 2026-09-16T23:29:45.744955+00:00 | 3.145 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [targeted-workflow-qt.log](reports/b71_apf7/targeted-workflow-qt.log) |
| 2026-09-16T23:29:59.385633+00:00 | 0.155 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [strict-before.log](reports/b71_apf7/strict-before.log) |
| 2026-09-16T23:29:59.400105+00:00 | 4.452 | 0 | `python3 reports/b71_apf7/screenshots.py after` | [screenshots-after-2.log](reports/b71_apf7/screenshots-after-2.log) |
| 2026-09-16T23:31:28.669151+00:00 | 7.161 | 0 | `python3 tests/mod_editor/test_apf_b711_overlay_books_qt.py` | [focused-qt.log](reports/b71_apf7/focused-qt.log) |
| 2026-09-16T23:32:08.323921+00:00 | 0.664 | 1 | `python3 tests/mod_editor/test_apf_b711_weight_preview.py` | [focused-preview.log](reports/b71_apf7/focused-preview.log) |
| 2026-09-16T23:33:03.671426+00:00 | 0.045 | 0 | `python3 reports/b71_apf2/hydrate_tools.py` | [hydrate-tools.log](reports/b71_apf7/hydrate-tools.log) |
| 2026-09-16T23:33:03.841231+00:00 | 0.651 | 0 | `python3 tests/mod_editor/test_apf_b711_weight_preview.py` | [focused-preview-2.log](reports/b71_apf7/focused-preview-2.log) |
| 2026-09-16T23:33:04.526006+00:00 | 21.152 | 0 | `python3 tests/mod_editor/test_apf_b711_book_scope.py` | [focused-books.log](reports/b71_apf7/focused-books.log) |
| 2026-09-16T23:33:05.026004+00:00 | 7.789 | 0 | `python3 tests/mod_editor/test_apf_b711_overlay_books_qt.py` | [focused-qt-2.log](reports/b71_apf7/focused-qt-2.log) |
| 2026-09-16T23:33:59.056088+00:00 | 11.274 | 0 | `python3 packaging/repin.py --apply` | [repin-implementation.log](reports/b71_apf7/repin-implementation.log) |
| 2026-09-16T23:34:11.382066+00:00 | 1513.355 | 0 | `.scratch/test-python/bin/python3 reports/b71_apf7/suites.py` | [all-suites.log](reports/b71_apf7/all-suites.log) |
| 2026-09-16T23:34:11.448484+00:00 | 1.263 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf2k8_coverage_tuning.py` | [test_apf2k8_coverage_tuning.log](reports/b71_apf7/test_apf2k8_coverage_tuning.log) |
| 2026-09-16T23:34:11.448532+00:00 | 0.47 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf2k8_playbook_route_writer.py` | [test_apf2k8_playbook_route_writer.log](reports/b71_apf7/test_apf2k8_playbook_route_writer.log) |
| 2026-09-16T23:34:11.449971+00:00 | 0.364 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_annotation_facade.py` | [test_apf_audio_annotation_facade.log](reports/b71_apf7/test_apf_audio_annotation_facade.log) |
| 2026-09-16T23:34:11.450305+00:00 | 0.628 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_all_crest_slots.py` | [test_apf_all_crest_slots.log](reports/b71_apf7/test_apf_all_crest_slots.log) |
| 2026-09-16T23:34:11.846609+00:00 | 0.301 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_annotations.py` | [test_apf_audio_annotations.log](reports/b71_apf7/test_apf_audio_annotations.log) |
| 2026-09-16T23:34:11.953398+00:00 | 0.194 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_batch_export.py` | [test_apf_audio_batch_export.log](reports/b71_apf7/test_apf_audio_batch_export.log) |
| 2026-09-16T23:34:12.112426+00:00 | 0.333 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_batch_facade.py` | [test_apf_audio_batch_facade.log](reports/b71_apf7/test_apf_audio_batch_facade.log) |
| 2026-09-16T23:34:12.181462+00:00 | 0.742 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_batch_gui.py` | [test_apf_audio_batch_gui.log](reports/b71_apf7/test_apf_audio_batch_gui.log) |
| 2026-09-16T23:34:12.184587+00:00 | 2.016 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_decode_cancellation.py` | [test_apf_audio_decode_cancellation.log](reports/b71_apf7/test_apf_audio_decode_cancellation.log) |
| 2026-09-16T23:34:12.483721+00:00 | 0.661 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_drop_zone_gui.py` | [test_apf_audio_drop_zone_gui.log](reports/b71_apf7/test_apf_audio_drop_zone_gui.log) |
| 2026-09-16T23:34:12.574737+00:00 | 4.571 | 0 | `python3 reports/b71_apf7/screenshots.py after` | [field-screenshots-final.log](reports/b71_apf7/field-screenshots-final.log) |
| 2026-09-16T23:34:12.745598+00:00 | 0.651 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_encoder_gui.py` | [test_apf_audio_encoder_gui.log](reports/b71_apf7/test_apf_audio_encoder_gui.log) |
| 2026-09-16T23:34:12.961580+00:00 | 11.225 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_encoding.py` | [test_apf_audio_encoding.log](reports/b71_apf7/test_apf_audio_encoding.log) |
| 2026-09-16T23:34:13.180220+00:00 | 4.019 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_import_idle_barrier.py` | [test_apf_audio_import_idle_barrier.log](reports/b71_apf7/test_apf_audio_import_idle_barrier.log) |
| 2026-09-16T23:34:13.429048+00:00 | 1.07 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_pcm_product_backend.py` | [test_apf_audio_pcm_product_backend.log](reports/b71_apf7/test_apf_audio_pcm_product_backend.log) |
| 2026-09-16T23:34:14.233222+00:00 | 0.63 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_replacement_pack.py` | [test_apf_audio_replacement_pack.log](reports/b71_apf7/test_apf_audio_replacement_pack.log) |
| 2026-09-16T23:34:14.529202+00:00 | 0.619 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_waveform_qt.py` | [test_apf_audio_waveform_qt.log](reports/b71_apf7/test_apf_audio_waveform_qt.log) |
| 2026-09-16T23:34:14.892745+00:00 | 0.256 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audo_exact_slot.py` | [test_apf_audo_exact_slot.log](reports/b71_apf7/test_apf_audo_exact_slot.log) |
| 2026-09-16T23:34:15.180057+00:00 | 0.306 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audo_product_backend.py` | [test_apf_audo_product_backend.log](reports/b71_apf7/test_apf_audo_product_backend.log) |
| 2026-09-16T23:34:15.181179+00:00 | 0.185 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audo_project.py` | [test_apf_audo_project.log](reports/b71_apf7/test_apf_audo_project.log) |
| 2026-09-16T23:34:15.398994+00:00 | 12.88 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ausb_exact_slot.py` | [test_apf_ausb_exact_slot.log](reports/b71_apf7/test_apf_ausb_exact_slot.log) |
| 2026-09-16T23:34:15.520807+00:00 | 0.339 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ausb_product_backend.py` | [test_apf_ausb_product_backend.log](reports/b71_apf7/test_apf_ausb_product_backend.log) |
| 2026-09-16T23:34:15.894830+00:00 | 28.367 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b661_book_content.py` | [test_apf_b661_book_content.log](reports/b71_apf7/test_apf_b661_book_content.log) |
| 2026-09-16T23:34:17.233318+00:00 | 0.423 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b661_ladder.py` | [test_apf_b661_ladder.log](reports/b71_apf7/test_apf_b661_ladder.log) |
| 2026-09-16T23:34:17.686338+00:00 | 2.609 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b66_appearance.py` | [test_apf_b66_appearance.log](reports/b71_apf7/test_apf_b66_appearance.log) |
| 2026-09-16T23:34:20.330214+00:00 | 5.334 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b66_personnel.py` | [test_apf_b66_personnel.log](reports/b71_apf7/test_apf_b66_personnel.log) |
| 2026-09-16T23:34:24.219532+00:00 | 69.573 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_books_qt.py` | [test_apf_b67_books_qt.log](reports/b71_apf7/test_apf_b67_books_qt.log) |
| 2026-09-16T23:34:25.696446+00:00 | 38.567 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_clone.py` | [test_apf_b67_clone.log](reports/b71_apf7/test_apf_b67_clone.log) |
| 2026-09-16T23:34:28.314091+00:00 | 156.616 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_defense_model_native.py` | [test_apf_b67_defense_model_native.log](reports/b71_apf7/test_apf_b67_defense_model_native.log) |
| 2026-09-16T23:34:44.291515+00:00 | 93.163 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_model_edges_native.py` | [test_apf_b67_model_edges_native.log](reports/b71_apf7/test_apf_b67_model_edges_native.log) |
| 2026-09-16T23:35:04.303884+00:00 | 1228.612 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_model_native.py` | [test_apf_b67_model_native.log](reports/b71_apf7/test_apf_b67_model_native.log) |
| 2026-09-16T23:35:21.992281+00:00 | 11.488 | 0 | `python3 packaging/repin.py --apply` | [repin-checkpoint.log](reports/b71_apf7/repin-checkpoint.log) |
| 2026-09-16T23:35:23.289945+00:00 | 6.677 | 0 | `python3 reports/b71_apf7/cpu_screenshots.py` | [cpu-screenshots.log](reports/b71_apf7/cpu-screenshots.log) |
| 2026-09-16T23:35:33.825090+00:00 | 0.131 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_static_audit.py` | [test_apf_b67_static_audit.log](reports/b71_apf7/test_apf_b67_static_audit.log) |
| 2026-09-16T23:35:33.990079+00:00 | 0.406 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_writers.py` | [test_apf_b67_writers.log](reports/b71_apf7/test_apf_b67_writers.log) |
| 2026-09-16T23:35:34.430515+00:00 | 332.665 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_writers_native.py` | [test_apf_b67_writers_native.log](reports/b71_apf7/test_apf_b67_writers_native.log) |
| 2026-09-16T23:36:11.418821+00:00 | 7.576 | 0 | `python3 tests/mod_editor/test_apf_b711_overlay_books_qt.py` | [refined-qt.log](reports/b71_apf7/refined-qt.log) |
| 2026-09-16T23:36:17.485681+00:00 | 0.269 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_xenia_patch.py` | [test_apf_b67_xenia_patch.log](reports/b71_apf7/test_apf_b67_xenia_patch.log) |
| 2026-09-16T23:36:17.786593+00:00 | 28.411 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_build.py` | [test_apf_b69_build.log](reports/b71_apf7/test_apf_b69_build.log) |
| 2026-09-16T23:36:19.025895+00:00 | 5.582 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [refined-existing-qt.log](reports/b71_apf7/refined-existing-qt.log) |
| 2026-09-16T23:36:46.229835+00:00 | 0.154 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_control_audit.py` | [test_apf_b69_control_audit.log](reports/b71_apf7/test_apf_b69_control_audit.log) |
| 2026-09-16T23:36:46.417204+00:00 | 78.811 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_editor_qt.py` | [test_apf_b69_editor_qt.log](reports/b71_apf7/test_apf_b69_editor_qt.log) |
| 2026-09-16T23:36:57.520642+00:00 | 10.31 | 0 | `python3 tests/mod_editor/test_provider_integrity.py` | [provider-integrity.log](reports/b71_apf7/provider-integrity.log) |
| 2026-09-16T23:36:59.107061+00:00 | 5.115 | 0 | `python3 reports/b71_apf7/cpu_screenshots.py` | [cpu-screenshots-final.log](reports/b71_apf7/cpu-screenshots-final.log) |
| 2026-09-16T23:37:04.964392+00:00 | 0.469 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_formation_calling.py` | [test_apf_b69_formation_calling.log](reports/b71_apf7/test_apf_b69_formation_calling.log) |
| 2026-09-16T23:37:05.467345+00:00 | 0.405 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_launch_patches.py` | [test_apf_b69_launch_patches.log](reports/b71_apf7/test_apf_b69_launch_patches.log) |
| 2026-09-16T23:37:05.907888+00:00 | 822.314 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_native.py` | [test_apf_b69_native.log](reports/b71_apf7/test_apf_b69_native.log) |
| 2026-09-16T23:37:07.863747+00:00 | 0.149 | 0 | `python3 tests/mod_editor/test_product_catalog.py` | [product-catalog.log](reports/b71_apf7/product-catalog.log) |
| 2026-09-16T23:37:08.046373+00:00 | 2.13 | 0 | `python3 tests/mod_editor/test_phase1_packaging.py` | [phase1-packaging.log](reports/b71_apf7/phase1-packaging.log) |
| 2026-09-16T23:37:10.229858+00:00 | 0.152 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [strict-final.log](reports/b71_apf7/strict-final.log) |
| 2026-09-16T23:37:49.366792+00:00 | 5.165 | 0 | `python3 reports/b71_apf7/cpu_screenshots.py` | [cpu-screenshots-final-2.log](reports/b71_apf7/cpu-screenshots-final-2.log) |
| 2026-09-16T23:38:05.262434+00:00 | 150.768 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_retirement_native.py` | [test_apf_b69_retirement_native.log](reports/b71_apf7/test_apf_b69_retirement_native.log) |
| 2026-09-16T23:38:16.239992+00:00 | 0.839 | 0 | `python3 tests/mod_editor/test_apf_browser_workspace_handoff.py` | [field-handoff-final.log](reports/b71_apf7/field-handoff-final.log) |
| 2026-09-16T23:38:17.111127+00:00 | 7.915 | 0 | `python3 tests/mod_editor/test_apf_b711_overlay_books_qt.py` | [field-layout-final.log](reports/b71_apf7/field-layout-final.log) |
| 2026-09-16T23:38:17.414626+00:00 | 2.185 | 0 | `python3 tests/mod_editor/test_studio_qt_models.py` | [studio-qt-models.log](reports/b71_apf7/studio-qt-models.log) |
| 2026-09-16T23:38:18.596667+00:00 | 18.553 | 0 | `python3 tests/mod_editor/test_apf_theme_layout_qt.py` | [apf-theme-final.log](reports/b71_apf7/apf-theme-final.log) |
| 2026-09-16T23:38:19.630826+00:00 | 45.316 | 0 | `python3 tests/mod_editor/test_studio_shell_layout_qt.py` | [studio-qt-shell.log](reports/b71_apf7/studio-qt-shell.log) |
| 2026-09-16T23:38:37.189689+00:00 | 11.585 | 0 | `python3 tests/mod_editor/test_apf_shell_search_accessibility_qt.py` | [apf-accessibility-final.log](reports/b71_apf7/apf-accessibility-final.log) |
| 2026-09-16T23:39:27.185591+00:00 | 7.896 | 0 | `python3 tests/mod_editor/test_apf_b711_overlay_books_qt.py` | [cpu-qt-final.log](reports/b71_apf7/cpu-qt-final.log) |
| 2026-09-16T23:39:35.114141+00:00 | 3.273 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [cpu-workflow-final.log](reports/b71_apf7/cpu-workflow-final.log) |
| 2026-09-16T23:39:38.422337+00:00 | 5.674 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [cpu-editor-final.log](reports/b71_apf7/cpu-editor-final.log) |
| 2026-09-16T23:39:48.072007+00:00 | 0.028 | 0 | `git --git-dir=.scratch/git diff --check` | [delivery-diff-check.log](reports/b71_apf7/delivery-diff-check.log) |
| 2026-09-16T23:39:48.128579+00:00 | 11.495 | 0 | `python3 packaging/repin.py --apply` | [repin-ui-final.log](reports/b71_apf7/repin-ui-final.log) |
| 2026-09-16T23:40:36.064407+00:00 | 36.368 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_schemes.py` | [test_apf_b69_schemes.log](reports/b71_apf7/test_apf_b69_schemes.log) |
| 2026-09-16T23:41:07.131199+00:00 | 0.434 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_wiring.py` | [test_apf_b69_wiring.log](reports/b71_apf7/test_apf_b69_wiring.log) |
| 2026-09-16T23:41:07.605150+00:00 | 196.936 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b70_stock_recipes.py` | [test_apf_b70_stock_recipes.log](reports/b71_apf7/test_apf_b70_stock_recipes.log) |
| 2026-09-16T23:41:12.467423+00:00 | 21.789 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b711_book_scope.py` | [test_apf_b711_book_scope.log](reports/b71_apf7/test_apf_b711_book_scope.log) |
| 2026-09-16T23:41:34.287070+00:00 | 7.591 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b711_overlay_books_qt.py` | [test_apf_b711_overlay_books_qt.log](reports/b71_apf7/test_apf_b711_overlay_books_qt.log) |
| 2026-09-16T23:41:41.773075+00:00 | 0.094 | 0 | `python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt .scratch/apf-release` | [release-stage.log](reports/b71_apf7/release-stage.log) |
| 2026-09-16T23:41:41.897043+00:00 | 0.386 | 0 | `env PYTHONDONTWRITEBYTECODE=1 python3 packaging/check_apf2k8_mod_studio_release.py .scratch/apf-release` | [release-check.log](reports/b71_apf7/release-check.log) |
| 2026-09-16T23:41:41.911472+00:00 | 0.664 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b711_weight_preview.py` | [test_apf_b711_weight_preview.log](reports/b71_apf7/test_apf_b711_weight_preview.log) |
| 2026-09-16T23:41:42.312780+00:00 | 10.408 | 0 | `env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/home/noah/2k-worktrees/astra-b71-apf7/.scratch/apf-release .scratch/test-python/bin/python3 .scratch/apf-release/packaging/check_apf2k8_mod_studio_runtime.py` | [release-runtime.log](reports/b71_apf7/release-runtime.log) |
| 2026-09-16T23:41:42.605452+00:00 | 2.707 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_editor_workflow.py` | [test_apf_b71_editor_workflow.log](reports/b71_apf7/test_apf_b71_editor_workflow.log) |
| 2026-09-16T23:41:45.343187+00:00 | 3.177 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [test_apf_b71_editor_workflow_qt.log](reports/b71_apf7/test_apf_b71_editor_workflow_qt.log) |
| 2026-09-16T23:41:48.554332+00:00 | 2.83 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask.py` | [test_apf_b71_situation_mask.log](reports/b71_apf7/test_apf_b71_situation_mask.log) |
| 2026-09-16T23:41:51.418634+00:00 | 4.209 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask_abi.py` | [test_apf_b71_situation_mask_abi.log](reports/b71_apf7/test_apf_b71_situation_mask_abi.log) |
| 2026-09-16T23:41:55.659684+00:00 | 1.264 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask_install.py` | [test_apf_b71_situation_mask_install.log](reports/b71_apf7/test_apf_b71_situation_mask_install.log) |
| 2026-09-16T23:41:56.953665+00:00 | 356.57 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask_native.py` | [test_apf_b71_situation_mask_native.log](reports/b71_apf7/test_apf_b71_situation_mask_native.log) |
| 2026-09-16T23:42:26.838334+00:00 | 5.657 | 0 | `python3 reports/b71_apf7/screenshots.py before` | [field-baseline-repro.log](reports/b71_apf7/field-baseline-repro.log) |
| 2026-09-16T23:42:32.524845+00:00 | 5.349 | 0 | `python3 reports/b71_apf7/screenshots.py after` | [field-all-tabs-final.log](reports/b71_apf7/field-all-tabs-final.log) |
| 2026-09-16T23:43:22.158937+00:00 | 0.029 | 0 | `python3 reports/b71_apf7/make_report.py` | [aggregate-progress.log](reports/b71_apf7/aggregate-progress.log) |
| 2026-09-16T23:44:24.573374+00:00 | 1.447 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask_qt.py` | [test_apf_b71_situation_mask_qt.log](reports/b71_apf7/test_apf_b71_situation_mask_qt.log) |
| 2026-09-16T23:44:26.051967+00:00 | 4.334 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situations.py` | [test_apf_b71_situations.log](reports/b71_apf7/test_apf_b71_situations.log) |
| 2026-09-16T23:44:30.417962+00:00 | 0.255 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_book_identity_qt.py` | [test_apf_book_identity_qt.log](reports/b71_apf7/test_apf_book_identity_qt.log) |
| 2026-09-16T23:44:30.707576+00:00 | 24.766 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_book_unlock.py` | [test_apf_book_unlock.log](reports/b71_apf7/test_apf_book_unlock.log) |
| 2026-09-16T23:44:54.948864+00:00 | 5.49 | 0 | `python3 reports/b71_apf7/screenshots.py before` | [field-baseline-tabs.log](reports/b71_apf7/field-baseline-tabs.log) |
| 2026-09-16T23:44:55.507961+00:00 | 0.146 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_book_unlock_retail.py` | [test_apf_book_unlock_retail.log](reports/b71_apf7/test_apf_book_unlock_retail.log) |
| 2026-09-16T23:44:55.687722+00:00 | 0.842 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_browser_workspace_handoff.py` | [test_apf_browser_workspace_handoff.log](reports/b71_apf7/test_apf_browser_workspace_handoff.log) |
| 2026-09-16T23:44:56.564077+00:00 | 0.32 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_build_ausb_overlays.py` | [test_apf_build_ausb_overlays.log](reports/b71_apf7/test_apf_build_ausb_overlays.log) |
| 2026-09-16T23:44:56.913776+00:00 | 0.311 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_build_raw_span_overlays.py` | [test_apf_build_raw_span_overlays.log](reports/b71_apf7/test_apf_build_raw_span_overlays.log) |
| 2026-09-16T23:44:57.258081+00:00 | 0.465 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_capability_action_parity.py` | [test_apf_capability_action_parity.log](reports/b71_apf7/test_apf_capability_action_parity.log) |
| 2026-09-16T23:44:57.758271+00:00 | 0.313 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_copied_volume_metadata.py` | [test_apf_copied_volume_metadata.log](reports/b71_apf7/test_apf_copied_volume_metadata.log) |
| 2026-09-16T23:44:58.102876+00:00 | 0.077 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_coverage_research_tools.py` | [test_apf_coverage_research_tools.log](reports/b71_apf7/test_apf_coverage_research_tools.log) |
| 2026-09-16T23:44:58.213331+00:00 | 2.889 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_cpu_audibles.py` | [test_apf_cpu_audibles.log](reports/b71_apf7/test_apf_cpu_audibles.log) |
| 2026-09-16T23:45:00.468223+00:00 | 5.308 | 0 | `python3 reports/b71_apf7/screenshots.py after` | [field-final-tabs.log](reports/b71_apf7/field-final-tabs.log) |
| 2026-09-16T23:45:01.136346+00:00 | 0.784 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_crest_budget_import.py` | [test_apf_crest_budget_import.log](reports/b71_apf7/test_apf_crest_budget_import.log) |
| 2026-09-16T23:45:01.954233+00:00 | 28.077 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_crest_fit.py` | [test_apf_crest_fit.log](reports/b71_apf7/test_apf_crest_fit.log) |
| 2026-09-16T23:45:30.061583+00:00 | 0.306 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_cross_domain_audio_safety.py` | [test_apf_cross_domain_audio_safety.log](reports/b71_apf7/test_apf_cross_domain_audio_safety.log) |
| 2026-09-16T23:45:30.397804+00:00 | 19.26 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_cubemap_face0_preview.py` | [test_apf_cubemap_face0_preview.log](reports/b71_apf7/test_apf_cubemap_face0_preview.log) |
| 2026-09-16T23:45:49.692584+00:00 | 0.287 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_custom_team_appearance_gui.py` | [test_apf_custom_team_appearance_gui.log](reports/b71_apf7/test_apf_custom_team_appearance_gui.log) |
| 2026-09-16T23:45:50.016426+00:00 | 6.981 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_custom_team_appearance_patch.py` | [test_apf_custom_team_appearance_patch.log](reports/b71_apf7/test_apf_custom_team_appearance_patch.log) |
| 2026-09-16T23:45:57.032504+00:00 | 0.512 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_defense_research_identity.py` | [test_apf_defense_research_identity.log](reports/b71_apf7/test_apf_defense_research_identity.log) |
| 2026-09-16T23:45:57.574957+00:00 | 137.353 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_defense_research_native.py` | [test_apf_defense_research_native.log](reports/b71_apf7/test_apf_defense_research_native.log) |
| 2026-09-16T23:47:34.666730+00:00 | 0.403 | 0 | `python3 -` | [legacy-label-census.log](reports/b71_apf7/legacy-label-census.log) |
| 2026-09-16T23:47:53.557495+00:00 | 0.336 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_digital_font.py` | [test_apf_digital_font.log](reports/b71_apf7/test_apf_digital_font.log) |
| 2026-09-16T23:47:53.924894+00:00 | 12.56 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_dxn_base_only_namefont.py` | [test_apf_dxn_base_only_namefont.log](reports/b71_apf7/test_apf_dxn_base_only_namefont.log) |
| 2026-09-16T23:48:06.516276+00:00 | 21.087 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_dxt5a_general_preview.py` | [test_apf_dxt5a_general_preview.log](reports/b71_apf7/test_apf_dxt5a_general_preview.log) |
| 2026-09-16T23:48:14.959237+00:00 | 37.326 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_endzone_dxt5a.py` | [test_apf_endzone_dxt5a.log](reports/b71_apf7/test_apf_endzone_dxt5a.log) |
| 2026-09-16T23:48:27.635206+00:00 | 0.121 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_export.py` | [test_apf_export.log](reports/b71_apf7/test_apf_export.log) |
| 2026-09-16T23:48:27.786008+00:00 | 0.342 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_external_audio_bank_bundle.py` | [test_apf_external_audio_bank_bundle.log](reports/b71_apf7/test_apf_external_audio_bank_bundle.log) |
| 2026-09-16T23:48:28.161302+00:00 | 0.179 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_art.py` | [test_apf_field_art.log](reports/b71_apf7/test_apf_field_art.log) |
| 2026-09-16T23:48:28.374308+00:00 | 0.847 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_art_gui.py` | [test_apf_field_art_gui.log](reports/b71_apf7/test_apf_field_art_gui.log) |
| 2026-09-16T23:48:29.254784+00:00 | 295.434 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_art_patch.py` | [test_apf_field_art_patch.log](reports/b71_apf7/test_apf_field_art_patch.log) |
| 2026-09-16T23:48:44.755470+00:00 | 0.684 | 1 | `python3 -` | [extended-label-capacity.log](reports/b71_apf7/extended-label-capacity.log) |
| 2026-09-16T23:48:52.322368+00:00 | 0.457 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_art_stock_label.py` | [test_apf_field_art_stock_label.log](reports/b71_apf7/test_apf_field_art_stock_label.log) |
| 2026-09-16T23:48:52.814726+00:00 | 203.065 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_extra_roundtrip.py` | [test_apf_field_extra_roundtrip.log](reports/b71_apf7/test_apf_field_extra_roundtrip.log) |
| 2026-09-16T23:48:54.961820+00:00 | 0.395 | 0 | `python3 -` | [extended-label-names.log](reports/b71_apf7/extended-label-names.log) |
| 2026-09-16T23:50:48.255932+00:00 | 0.53 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_material_project.py` | [test_apf_field_material_project.log](reports/b71_apf7/test_apf_field_material_project.log) |
| 2026-09-16T23:50:48.820437+00:00 | 0.325 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_material_writer.py` | [test_apf_field_material_writer.log](reports/b71_apf7/test_apf_field_material_writer.log) |
| 2026-09-16T23:50:49.180082+00:00 | 0.333 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_formation_alignment_writer.py` | [test_apf_formation_alignment_writer.log](reports/b71_apf7/test_apf_formation_alignment_writer.log) |
| 2026-09-16T23:50:49.546126+00:00 | 0.208 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_fourth_down.py` | [test_apf_fourth_down.log](reports/b71_apf7/test_apf_fourth_down.log) |
| 2026-09-16T23:50:49.788014+00:00 | 102.227 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_fourth_down_native.py` | [test_apf_fourth_down_native.log](reports/b71_apf7/test_apf_fourth_down_native.log) |
| 2026-09-16T23:52:15.911699+00:00 | 0.181 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_fourth_down_qt.py` | [test_apf_fourth_down_qt.log](reports/b71_apf7/test_apf_fourth_down_qt.log) |
| 2026-09-16T23:52:16.123774+00:00 | 0.044 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_full_shell_visual_gate.py` | [test_apf_full_shell_visual_gate.log](reports/b71_apf7/test_apf_full_shell_visual_gate.log) |
| 2026-09-16T23:52:16.197903+00:00 | 0.493 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_g12_surfaces.py` | [test_apf_g12_surfaces.log](reports/b71_apf7/test_apf_g12_surfaces.log) |
| 2026-09-16T23:52:16.725363+00:00 | 1.424 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_helmet_crest_design_product.py` | [test_apf_helmet_crest_design_product.log](reports/b71_apf7/test_apf_helmet_crest_design_product.log) |
| 2026-09-16T23:52:18.182876+00:00 | 7.19 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_helmet_logo_placement.py` | [test_apf_helmet_logo_placement.log](reports/b71_apf7/test_apf_helmet_logo_placement.log) |
| 2026-09-16T23:52:20.284976+00:00 | 10.337 | 0 | `python3 -` | [per-side-label-capacity.log](reports/b71_apf7/per-side-label-capacity.log) |
| 2026-09-16T23:52:25.404480+00:00 | 4.049 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_helmet_logo_regions.py` | [test_apf_helmet_logo_regions.log](reports/b71_apf7/test_apf_helmet_logo_regions.log) |
| 2026-09-16T23:52:29.487831+00:00 | 1.218 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_helmet_logo_regions_qt.py` | [test_apf_helmet_logo_regions_qt.log](reports/b71_apf7/test_apf_helmet_logo_regions_qt.log) |
| 2026-09-16T23:52:30.737279+00:00 | 0.608 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_import_offers_resize.py` | [test_apf_import_offers_resize.log](reports/b71_apf7/test_apf_import_offers_resize.log) |
| 2026-09-16T23:52:31.378280+00:00 | 0.205 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_iso_extraction_is_layout_tolerant.py` | [test_apf_iso_extraction_is_layout_tolerant.log](reports/b71_apf7/test_apf_iso_extraction_is_layout_tolerant.log) |
| 2026-09-16T23:52:31.614296+00:00 | 0.058 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_linear_txtr_png.py` | [test_apf_linear_txtr_png.log](reports/b71_apf7/test_apf_linear_txtr_png.log) |
| 2026-09-16T23:52:31.703065+00:00 | 13.659 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_logo_patch.py` | [test_apf_logo_patch.log](reports/b71_apf7/test_apf_logo_patch.log) |
| 2026-09-16T23:52:32.049291+00:00 | 0.087 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_logo_surface_ownership.py` | [test_apf_logo_surface_ownership.log](reports/b71_apf7/test_apf_logo_surface_ownership.log) |
| 2026-09-16T23:52:32.165643+00:00 | 42.906 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_logocache_patch.py` | [test_apf_logocache_patch.log](reports/b71_apf7/test_apf_logocache_patch.log) |
| 2026-09-16T23:52:45.400063+00:00 | 0.182 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_mask_preview_alpha.py` | [test_apf_mask_preview_alpha.log](reports/b71_apf7/test_apf_mask_preview_alpha.log) |
| 2026-09-16T23:52:45.614263+00:00 | 2.716 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_model_export_gui.py` | [test_apf_model_export_gui.log](reports/b71_apf7/test_apf_model_export_gui.log) |
| 2026-09-16T23:52:48.365256+00:00 | 51.918 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_model_import.py` | [test_apf_model_import.log](reports/b71_apf7/test_apf_model_import.log) |
| 2026-09-16T23:53:15.102392+00:00 | 2.169 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_number_encode_defaults.py` | [test_apf_number_encode_defaults.log](reports/b71_apf7/test_apf_number_encode_defaults.log) |
| 2026-09-16T23:53:17.302913+00:00 | 262.544 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_number_texture_writer.py` | [test_apf_number_texture_writer.log](reports/b71_apf7/test_apf_number_texture_writer.log) |
| 2026-09-16T23:53:24.723220+00:00 | 1.301 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_package_map_writer.py` | [test_apf_package_map_writer.log](reports/b71_apf7/test_apf_package_map_writer.log) |
| 2026-09-16T23:53:25.341867+00:00 | 32.22 | 0 | `python3 tests/mod_editor/test_apf_b711_book_scope.py` | [final-book-capacity.log](reports/b71_apf7/final-book-capacity.log) |
| 2026-09-16T23:53:26.054189+00:00 | 0.505 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_pass_fetch_export_qt.py` | [test_apf_pass_fetch_export_qt.log](reports/b71_apf7/test_apf_pass_fetch_export_qt.log) |
| 2026-09-16T23:53:26.523959+00:00 | 7.455 | 0 | `python3 tests/mod_editor/test_apf_b711_overlay_books_qt.py` | [final-overlay-and-weights.log](reports/b71_apf7/final-overlay-and-weights.log) |
| 2026-09-16T23:53:26.590140+00:00 | 12.772 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_play_designer.py` | [test_apf_play_designer.log](reports/b71_apf7/test_apf_play_designer.log) |
| 2026-09-16T23:53:39.397023+00:00 | 0.48 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_play_designer_project.py` | [test_apf_play_designer_project.log](reports/b71_apf7/test_apf_play_designer_project.log) |
| 2026-09-16T23:53:39.909721+00:00 | 0.323 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_play_designer_qt.py` | [test_apf_play_designer_qt.log](reports/b71_apf7/test_apf_play_designer_qt.log) |
| 2026-09-16T23:53:40.267824+00:00 | 0.327 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playbook_route_gui.py` | [test_apf_playbook_route_gui.log](reports/b71_apf7/test_apf_playbook_route_gui.log) |
| 2026-09-16T23:53:40.313600+00:00 | 1.93 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcall_patch.py` | [test_apf_playcall_patch.log](reports/b71_apf7/test_apf_playcall_patch.log) |
| 2026-09-16T23:53:40.629737+00:00 | 218.188 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcall_research_native.py` | [test_apf_playcall_research_native.log](reports/b71_apf7/test_apf_playcall_research_native.log) |
| 2026-09-16T23:53:42.277694+00:00 | 92.114 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcalling_editor_build.py` | [test_apf_playcalling_editor_build.log](reports/b71_apf7/test_apf_playcalling_editor_build.log) |
| 2026-09-16T23:54:25.307590+00:00 | 4.939 | 0 | `python3 reports/b71_apf7/cpu_screenshots.py` | [final-cpu-screenshots.log](reports/b71_apf7/final-cpu-screenshots.log) |
| 2026-09-16T23:54:26.478910+00:00 | 10.691 | 0 | `python3 packaging/repin.py --apply` | [repin-capacity.log](reports/b71_apf7/repin-capacity.log) |
| 2026-09-16T23:55:14.424923+00:00 | 1.362 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcalling_editor_facade.py` | [test_apf_playcalling_editor_facade.log](reports/b71_apf7/test_apf_playcalling_editor_facade.log) |
| 2026-09-16T23:55:15.822322+00:00 | 0.522 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcalling_editor_patches.py` | [test_apf_playcalling_editor_patches.log](reports/b71_apf7/test_apf_playcalling_editor_patches.log) |
| 2026-09-16T23:55:16.378075+00:00 | 5.322 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [test_apf_playcalling_editor_qt.log](reports/b71_apf7/test_apf_playcalling_editor_qt.log) |
| 2026-09-16T23:55:21.734075+00:00 | 6.751 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_position_patch.py` | [test_apf_player_position_patch.log](reports/b71_apf7/test_apf_player_position_patch.log) |
| 2026-09-16T23:55:28.515346+00:00 | 20.103 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_position_product_backend.py` | [test_apf_player_position_product_backend.log](reports/b71_apf7/test_apf_player_position_product_backend.log) |
| 2026-09-16T23:55:32.949014+00:00 | 0.107 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_positions.py` | [test_apf_player_positions.log](reports/b71_apf7/test_apf_player_positions.log) |
| 2026-09-16T23:55:33.089631+00:00 | 4.261 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_rating_patch.py` | [test_apf_player_rating_patch.log](reports/b71_apf7/test_apf_player_rating_patch.log) |
| 2026-09-16T23:55:37.381630+00:00 | 9.084 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_rating_product_backend.py` | [test_apf_player_rating_product_backend.log](reports/b71_apf7/test_apf_player_rating_product_backend.log) |
| 2026-09-16T23:55:46.500586+00:00 | 14.621 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_rating_sheet_import.py` | [test_apf_player_rating_sheet_import.log](reports/b71_apf7/test_apf_player_rating_sheet_import.log) |
| 2026-09-16T23:55:48.651955+00:00 | 0.801 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_ratings.py` | [test_apf_player_ratings.log](reports/b71_apf7/test_apf_player_ratings.log) |
| 2026-09-16T23:55:49.483367+00:00 | 0.156 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_product_findings.py` | [test_apf_product_findings.log](reports/b71_apf7/test_apf_product_findings.log) |
| 2026-09-16T23:55:49.673209+00:00 | 0.713 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_product_findings_gui.py` | [test_apf_product_findings_gui.log](reports/b71_apf7/test_apf_product_findings_gui.log) |
| 2026-09-16T23:55:50.419051+00:00 | 0.228 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_product_validation_wrappers.py` | [test_apf_product_validation_wrappers.log](reports/b71_apf7/test_apf_product_validation_wrappers.log) |
| 2026-09-16T23:55:50.682678+00:00 | 31.038 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_project_document_workflow.py` | [test_apf_project_document_workflow.log](reports/b71_apf7/test_apf_project_document_workflow.log) |
| 2026-09-16T23:56:01.154911+00:00 | 0.198 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_project_streaming.py` | [test_apf_project_streaming.log](reports/b71_apf7/test_apf_project_streaming.log) |
| 2026-09-16T23:56:01.387297+00:00 | 1.101 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_probes.py` | [test_apf_ps3_probes.log](reports/b71_apf7/test_apf_ps3_probes.log) |
| 2026-09-16T23:56:02.518105+00:00 | 16.84 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_roster_convert.py` | [test_apf_ps3_roster_convert.log](reports/b71_apf7/test_apf_ps3_roster_convert.log) |
| 2026-09-16T23:56:19.391109+00:00 | 1.582 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_roster_import_qt.py` | [test_apf_ps3_roster_import_qt.log](reports/b71_apf7/test_apf_ps3_roster_import_qt.log) |
| 2026-09-16T23:56:21.002743+00:00 | 3.782 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_speed.py` | [test_apf_ps3_speed.log](reports/b71_apf7/test_apf_ps3_speed.log) |
| 2026-09-16T23:56:21.754524+00:00 | 10.176 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_speed_packages.py` | [test_apf_ps3_speed_packages.log](reports/b71_apf7/test_apf_ps3_speed_packages.log) |
| 2026-09-16T23:56:24.816059+00:00 | 29.517 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_texture_bundle.py` | [test_apf_ps3_texture_bundle.log](reports/b71_apf7/test_apf_ps3_texture_bundle.log) |
| 2026-09-16T23:56:28.967953+00:00 | 0.267 | 1 | `python3 tests/mod_editor/test_apf_book_identity_qt.py` | [manual-books-qt.log](reports/b71_apf7/manual-books-qt.log) |
| 2026-09-16T23:56:29.346856+00:00 | 7.54 | 0 | `python3 tests/mod_editor/test_apf_b711_overlay_books_qt.py` | [manual-handoff-qt.log](reports/b71_apf7/manual-handoff-qt.log) |
| 2026-09-16T23:56:31.961234+00:00 | 0.412 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_texture_bundle_qt.py` | [test_apf_ps3_texture_bundle_qt.log](reports/b71_apf7/test_apf_ps3_texture_bundle_qt.log) |
| 2026-09-16T23:56:32.408007+00:00 | 0.16 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_public_docs_registry_current.py` | [test_apf_public_docs_registry_current.log](reports/b71_apf7/test_apf_public_docs_registry_current.log) |
| 2026-09-16T23:56:32.599054+00:00 | 0.183 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_rating_value_domains.py` | [test_apf_rating_value_domains.log](reports/b71_apf7/test_apf_rating_value_domains.log) |
| 2026-09-16T23:56:32.815016+00:00 | 0.044 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_retail_crest_channel_audit.py` | [test_apf_retail_crest_channel_audit.log](reports/b71_apf7/test_apf_retail_crest_channel_audit.log) |
| 2026-09-16T23:56:32.889716+00:00 | 8.214 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_appearance_transfer.py` | [test_apf_roster_appearance_transfer.log](reports/b71_apf7/test_apf_roster_appearance_transfer.log) |
| 2026-09-16T23:56:40.566539+00:00 | 0.284 | 0 | `python3 tests/mod_editor/test_apf_book_identity_qt.py` | [final-manual-books-qt.log](reports/b71_apf7/final-manual-books-qt.log) |
| 2026-09-16T23:56:41.137077+00:00 | 5.039 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_appearance_transfer_qt.py` | [test_apf_roster_appearance_transfer_qt.log](reports/b71_apf7/test_apf_roster_appearance_transfer_qt.log) |
| 2026-09-16T23:56:46.207167+00:00 | 11.253 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_identity.py` | [test_apf_roster_identity.log](reports/b71_apf7/test_apf_roster_identity.log) |
| 2026-09-16T23:56:54.367417+00:00 | 1.717 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_identity_gui.py` | [test_apf_roster_identity_gui.log](reports/b71_apf7/test_apf_roster_identity_gui.log) |
| 2026-09-16T23:56:56.118967+00:00 | 0.141 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_workspace.py` | [test_apf_roster_workspace.log](reports/b71_apf7/test_apf_roster_workspace.log) |
| 2026-09-16T23:56:56.294383+00:00 | 0.364 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_workspace_gui.py` | [test_apf_roster_workspace_gui.log](reports/b71_apf7/test_apf_roster_workspace_gui.log) |
| 2026-09-16T23:56:56.689943+00:00 | 1.255 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_save_playbook_assignments_gui.py` | [test_apf_save_playbook_assignments_gui.log](reports/b71_apf7/test_apf_save_playbook_assignments_gui.log) |
| 2026-09-16T23:56:57.495040+00:00 | 4.462 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_save_roster_players.py` | [test_apf_save_roster_players.log](reports/b71_apf7/test_apf_save_roster_players.log) |
| 2026-09-16T23:56:57.979944+00:00 | 0.728 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_save_roster_players_gui.py` | [test_apf_save_roster_players_gui.log](reports/b71_apf7/test_apf_save_roster_players_gui.log) |
| 2026-09-16T23:56:58.742552+00:00 | 0.557 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_scorebug_workspace_qt.py` | [test_apf_scorebug_workspace_qt.log](reports/b71_apf7/test_apf_scorebug_workspace_qt.log) |
| 2026-09-16T23:56:59.333390+00:00 | 10.922 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_shell_search_accessibility_qt.py` | [test_apf_shell_search_accessibility_qt.log](reports/b71_apf7/test_apf_shell_search_accessibility_qt.log) |
| 2026-09-16T23:57:02.011072+00:00 | 0.587 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_splb_add_multiple_formations.py` | [test_apf_splb_add_multiple_formations.log](reports/b71_apf7/test_apf_splb_add_multiple_formations.log) |
| 2026-09-16T23:57:02.631537+00:00 | 1.105 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_splb_formation_personnel.py` | [test_apf_splb_formation_personnel.log](reports/b71_apf7/test_apf_splb_formation_personnel.log) |
| 2026-09-16T23:57:03.769909+00:00 | 2.269 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_splb_tag_reassignment.py` | [test_apf_splb_tag_reassignment.log](reports/b71_apf7/test_apf_splb_tag_reassignment.log) |
| 2026-09-16T23:57:06.069457+00:00 | 0.36 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_splb_writer.py` | [test_apf_splb_writer.log](reports/b71_apf7/test_apf_splb_writer.log) |
| 2026-09-16T23:57:06.463829+00:00 | 0.105 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_material_findings.py` | [test_apf_stadium_material_findings.log](reports/b71_apf7/test_apf_stadium_material_findings.log) |
| 2026-09-16T23:57:06.599057+00:00 | 0.287 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_model_import.py` | [test_apf_stadium_model_import.log](reports/b71_apf7/test_apf_stadium_model_import.log) |
| 2026-09-16T23:57:06.920155+00:00 | 0.234 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_studio.py` | [test_apf_stadium_studio.log](reports/b71_apf7/test_apf_stadium_studio.log) |
| 2026-09-16T23:57:07.187890+00:00 | 0.532 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_studio_gui.py` | [test_apf_stadium_studio_gui.log](reports/b71_apf7/test_apf_stadium_studio_gui.log) |
| 2026-09-16T23:57:07.750789+00:00 | 73.718 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_texture.py` | [test_apf_stadium_texture.log](reports/b71_apf7/test_apf_stadium_texture.log) |
| 2026-09-16T23:57:10.288784+00:00 | 0.631 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stfs_roster_rehash.py` | [test_apf_stfs_roster_rehash.log](reports/b71_apf7/test_apf_stfs_roster_rehash.log) |
| 2026-09-16T23:57:10.950644+00:00 | 1.11 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_audio_gui.py` | [test_apf_studio_audio_gui.log](reports/b71_apf7/test_apf_studio_audio_gui.log) |
| 2026-09-16T23:57:12.094957+00:00 | 0.239 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_core.py` | [test_apf_studio_core.log](reports/b71_apf7/test_apf_studio_core.log) |
| 2026-09-16T23:57:12.367501+00:00 | 0.523 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_draft_logo.py` | [test_apf_studio_draft_logo.log](reports/b71_apf7/test_apf_studio_draft_logo.log) |
| 2026-09-16T23:57:12.924334+00:00 | 2.273 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_inspectors.py` | [test_apf_studio_inspectors.log](reports/b71_apf7/test_apf_studio_inspectors.log) |
| 2026-09-16T23:57:15.232076+00:00 | 14.846 | 0 | `env -u PYTHONPATH /home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_installer.py` | [test_apf_studio_installer.log](reports/b71_apf7/test_apf_studio_installer.log) |
| 2026-09-16T23:57:18.852124+00:00 | 0.446 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_safety.py` | [test_apf_studio_safety.log](reports/b71_apf7/test_apf_studio_safety.log) |
| 2026-09-16T23:57:19.329556+00:00 | 0.547 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_text_edit.py` | [test_apf_studio_text_edit.log](reports/b71_apf7/test_apf_studio_text_edit.log) |
| 2026-09-16T23:57:19.909337+00:00 | 9.971 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_team_art.py` | [test_apf_team_art.log](reports/b71_apf7/test_apf_team_art.log) |
| 2026-09-16T23:57:21.707777+00:00 | 5.205 | 0 | `python3 reports/b71_apf7/cpu_screenshots.py` | [final-cpu-and-books-screenshots.log](reports/b71_apf7/final-cpu-and-books-screenshots.log) |
| 2026-09-16T23:57:21.730457+00:00 | 1.29 | 0 | `python3 reports/b71_apf7/manual_screenshots.py` | [final-manual-screenshots.log](reports/b71_apf7/final-manual-screenshots.log) |
| 2026-09-16T23:57:21.747099+00:00 | 41.734 | 0 | `python3 tests/mod_editor/test_studio_shell_layout_qt.py` | [final-manual-shell-layout.log](reports/b71_apf7/final-manual-shell-layout.log) |
| 2026-09-16T23:57:21.749354+00:00 | 5.35 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [final-cpu-manual-workflow.log](reports/b71_apf7/final-cpu-manual-workflow.log) |
| 2026-09-16T23:57:29.914975+00:00 | 0.527 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_team_art_qt.py` | [test_apf_team_art_qt.log](reports/b71_apf7/test_apf_team_art_qt.log) |
| 2026-09-16T23:57:30.110377+00:00 | 0.603 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_team_crest_selection.py` | [test_apf_team_crest_selection.log](reports/b71_apf7/test_apf_team_crest_selection.log) |
| 2026-09-16T23:57:30.475666+00:00 | 2.018 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_team_logo_gui.py` | [test_apf_team_logo_gui.log](reports/b71_apf7/test_apf_team_logo_gui.log) |
| 2026-09-16T23:57:30.748581+00:00 | 0.532 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_text_sheet_gui.py` | [test_apf_text_sheet_gui.log](reports/b71_apf7/test_apf_text_sheet_gui.log) |
| 2026-09-16T23:57:31.315462+00:00 | 0.686 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_textlogo_gui.py` | [test_apf_textlogo_gui.log](reports/b71_apf7/test_apf_textlogo_gui.log) |
| 2026-09-16T23:57:32.034999+00:00 | 58.241 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_textlogo_writer.py` | [test_apf_textlogo_writer.log](reports/b71_apf7/test_apf_textlogo_writer.log) |
| 2026-09-16T23:57:32.524592+00:00 | 17.768 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_theme_layout_qt.py` | [test_apf_theme_layout_qt.log](reports/b71_apf7/test_apf_theme_layout_qt.log) |
| 2026-09-16T23:57:39.881349+00:00 | 1.405 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_allocation_capacity.py` | [test_apf_uniform_allocation_capacity.log](reports/b71_apf7/test_apf_uniform_allocation_capacity.log) |
| 2026-09-16T23:57:41.321689+00:00 | 7.49 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_equipment_colors.py` | [test_apf_uniform_equipment_colors.log](reports/b71_apf7/test_apf_uniform_equipment_colors.log) |
| 2026-09-16T23:57:48.849229+00:00 | 0.196 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_equipment_colors_gui.py` | [test_apf_uniform_equipment_colors_gui.log](reports/b71_apf7/test_apf_uniform_equipment_colors_gui.log) |
| 2026-09-16T23:57:49.078963+00:00 | 1.447 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_independence.py` | [test_apf_uniform_independence.log](reports/b71_apf7/test_apf_uniform_independence.log) |
| 2026-09-16T23:57:50.327648+00:00 | 2.395 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_inventory_gui.py` | [test_apf_uniform_inventory_gui.log](reports/b71_apf7/test_apf_uniform_inventory_gui.log) |
| 2026-09-16T23:57:50.560826+00:00 | 13.571 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_wave_integration.py` | [test_apf_wave_integration.log](reports/b71_apf7/test_apf_wave_integration.log) |
| 2026-09-16T23:57:52.753761+00:00 | 0.147 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_wordmark_regions.py` | [test_apf_wordmark_regions.log](reports/b71_apf7/test_apf_wordmark_regions.log) |
| 2026-09-16T23:57:52.933109+00:00 | 65.171 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_workspace_recovery.py` | [test_apf_workspace_recovery.log](reports/b71_apf7/test_apf_workspace_recovery.log) |
| 2026-09-16T23:58:04.166290+00:00 | 0.162 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xenia_edge.py` | [test_apf_xenia_edge.log](reports/b71_apf7/test_apf_xenia_edge.log) |
| 2026-09-16T23:58:04.358991+00:00 | 1.744 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xenos_4444_mip_layout.py` | [test_apf_xenos_4444_mip_layout.log](reports/b71_apf7/test_apf_xenos_4444_mip_layout.log) |
| 2026-09-16T23:58:06.137356+00:00 | 0.079 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xenos_4444_png.py` | [test_apf_xenos_4444_png.log](reports/b71_apf7/test_apf_xenos_4444_png.log) |
| 2026-09-16T23:58:06.246214+00:00 | 0.081 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xenos_extra_formats_png.py` | [test_apf_xenos_extra_formats_png.log](reports/b71_apf7/test_apf_xenos_extra_formats_png.log) |
| 2026-09-16T23:58:06.356857+00:00 | 1.062 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xex_image.py` | [test_apf_xex_image.log](reports/b71_apf7/test_apf_xex_image.log) |
| 2026-09-16T23:58:07.452834+00:00 | 72.2 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xex_image_retail.py` | [test_apf_xex_image_retail.log](reports/b71_apf7/test_apf_xex_image_retail.log) |
| 2026-09-16T23:58:21.502441+00:00 | 1.778 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xma1_wizard_gui.py` | [test_apf_xma1_wizard_gui.log](reports/b71_apf7/test_apf_xma1_wizard_gui.log) |
| 2026-09-16T23:58:23.313653+00:00 | 39.278 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_b69_a1_playcalling.py` | [test_b69_a1_playcalling.log](reports/b71_apf7/test_b69_a1_playcalling.log) |
| 2026-09-16T23:58:30.310455+00:00 | 9.966 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_provider_integrity.py` | [test_provider_integrity.log](reports/b71_apf7/test_provider_integrity.log) |
| 2026-09-16T23:58:40.310166+00:00 | 0.145 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_product_catalog.py` | [test_product_catalog.log](reports/b71_apf7/test_product_catalog.log) |
| 2026-09-16T23:58:40.487806+00:00 | 2.047 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_phase1_packaging.py` | [test_phase1_packaging.log](reports/b71_apf7/test_phase1_packaging.log) |
| 2026-09-16T23:58:42.566763+00:00 | 0.093 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_capability_registry_module_commands.py` | [test_capability_registry_module_commands.log](reports/b71_apf7/test_capability_registry_module_commands.log) |
| 2026-09-16T23:58:42.689824+00:00 | 0.875 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_studio_qt_models.py` | [test_studio_qt_models.log](reports/b71_apf7/test_studio_qt_models.log) |
| 2026-09-16T23:58:43.598729+00:00 | 41.12 | 0 | `/home/noah/2k-worktrees/astra-b71-apf7/.scratch/test-python/bin/python3 tests/mod_editor/test_studio_shell_layout_qt.py` | [test_studio_shell_layout_qt.log](reports/b71_apf7/test_studio_shell_layout_qt.log) |
| 2026-09-16T23:59:27.547944+00:00 | 2.95 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [final-manual-workflow-qt.log](reports/b71_apf7/final-manual-workflow-qt.log) |
| 2026-09-16T23:59:27.568923+00:00 | 10.425 | 0 | `python3 packaging/repin.py --apply` | [repin-manual-access.log](reports/b71_apf7/repin-manual-access.log) |
| 2026-09-16T23:59:27.572453+00:00 | 0.148 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [strict-manual-access.log](reports/b71_apf7/strict-manual-access.log) |
| 2026-09-16T23:59:38.106809+00:00 | 0.093 | 0 | `git --git-dir=.scratch/git --work-tree=. commit -m 'Restore manual allocation access and document the real book pool' -- mod_editor/apf_studio/book_identity_qt.py mod_editor/apf_studio/gui.py mod_editor/apf_studio/playcalling_editor_qt.py mod_editor/apf_studio/playcalling_service.py docs/mod_editor/apf2k8_book_identity_walkthrough.md docs/mod_editor/apf2k8_mod_studio_changelog.md tests/mod_editor/test_apf_b711_book_scope.py tests/mod_editor/test_apf_b711_overlay_books_qt.py tests/mod_editor/test_apf_book_identity_qt.py` | [commit-manual-access.log](reports/b71_apf7/commit-manual-access.log) |
| 2026-09-16T23:59:51.120160+00:00 | 0.084 | 0 | `python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt .scratch/apf-release-final` | [release-stage-final.log](reports/b71_apf7/release-stage-final.log) |
| 2026-09-17T00:00:19.214948+00:00 | 0.379 | 0 | `env PYTHONDONTWRITEBYTECODE=1 python3 packaging/check_apf2k8_mod_studio_release.py .scratch/apf-release-final` | [release-check-final.log](reports/b71_apf7/release-check-final.log) |
| 2026-09-17T00:00:19.230477+00:00 | 9.803 | 0 | `env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/home/noah/2k-worktrees/astra-b71-apf7/.scratch/apf-release-final .scratch/test-python/bin/python3 .scratch/apf-release-final/packaging/check_apf2k8_mod_studio_runtime.py` | [release-runtime-final.log](reports/b71_apf7/release-runtime-final.log) |
| 2026-09-17T00:01:42.419237+00:00 | 0.033 | 1 | `python3 reports/b71_apf7/make_report.py --require-pass` | [final-report-aggregate.log](reports/b71_apf7/final-report-aggregate.log) |
| 2026-09-17T00:02:02.341286+00:00 | 0.035 | 0 | `python3 reports/b71_apf7/make_report.py --require-pass` | [final-report-aggregate-checked.log](reports/b71_apf7/final-report-aggregate-checked.log) |

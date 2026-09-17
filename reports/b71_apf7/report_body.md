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

<!-- RESULTS -->

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

<!-- COMMANDS -->

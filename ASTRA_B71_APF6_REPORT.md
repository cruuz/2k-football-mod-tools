# Beta 71 APF-6: CPU Play Calling workflow

Branch **astra/b71-apf6-editor-workflow**, based on integrated A7 **cea8a3c85db408dafeea15b361faee9d05be33a7**.
Implementation is committed in `.scratch/git`; the shared worktree git directory
is unchanged. Delivery bundle: `.scratch/astra-b71-apf6.bundle`. No push,
emulator, desktop display, audio or disc build. Qt uses `offscreen`.

## Result

**196/196 requested standalone suite files pass** on their latest complete run,
reporting **1869 tests and 11 explicit skips**.
The full matrix is [suite_results.json](reports/b71_apf6/suite_results.json).
All required final checks pass.

The editor retains parsed source books and validated receipts, confirms edits
without a separate Review click, and collects mixed changes in **Pending edits**.
**Confirm all** runs existing reviews plus cross-edit checks and writes the
independent clean set as one atomic recipe and one Undo step. Blocked dependencies
remain pending, with the edit, location, reason and fix displayed together.
Each pending row has **Undo / clear**. MASTER retains its experimental all-books warning.

## Profile and timings: PROVED on this Linux host

[profile.py](reports/b71_apf6/profile.py) uses the owned export at
`/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A`. The source index SHA-256 is
`dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e` in every run. Nothing writes or copies the retail
source. The baseline loads the three original Python modules directly from the
recorded A7 commit; the same process driver then performs 21 play-rating edits,
21 formation-rating edits and 21 balanced-audible edits in O-ManBlock. Each timed
edit includes review, stage and the complete offscreen CPU-page refresh.
No disk-cache flush is claimed. First load is a separate fresh-process measurement.

| Run | First load, s | 63 edits, s | Mean/edit, s | Slowest/edit, s |
| --- | ---: | ---: | ---: | ---: |
| A7 baseline, same repeated-formation sequence | 6.250 | 447.141 | 7.097 | 9.976 |
| Final incremental code, identical sequence | 2.696 | 8.863 | 0.141 | 0.363 |
| New Confirm buttons, cycling formations and shell CPU refresh callback | 2.750 | 14.041 | 0.223 | 0.361 |

The identical sequence is **50.4× faster** here.
The varied run invokes the page's Confirm path and connects `modifiedChanged` to
`set_context`, exercising the synchronous CPU reset used by the shell plus the
panel refresh. It is a real-export page measurement, not a complete timed session
of every other studio workspace, file picker, autosave and operating-system UI.
The exact historic 63 requests were not supplied; this is a reproducible mixed
pattern matching the reported edit types and count, not a claim to reconstruct
that private session. Native Windows/macOS performance remains UNWITNESSED.
Some baseline intervals overlapped short development checks and later optimized
runs overlapped detached regression processes; all wall times are retained, and
the counters independently establish elimination of the repeated catalog/replay work.

Bulk on the same export, cycling formations: all 63 additions to Pending edits
used **0.395s** total (slowest addition **0.031s**).
One **Confirm all** checked/staged those 63 requests and refreshed the page in
**1.735s**, with exactly one Undo entry. Source reads
occurred once. This total includes every writer check; no check is deferred to
an optional Review click.

### Timed phases

These times are inclusive and overlap; do not add them. Counts include cold load
and selection refreshes. Ledger access counts include cached lookups, not just
physical reads. MASTER's cached wrapper calls the original reader once, so the
after counter includes both wrapper and cold inner call.

| Phase | Before calls | Before seconds | After calls | After seconds |
| --- | ---: | ---: | ---: | ---: |
| source books | 191 | 137.258 | 1 | 0.689 |
| MASTER inventory | 191 | 15.762 | 2 | 0.164 |
| base state | 191 | 200.880 | 1 | 0.772 |
| ledger read | 1816 | 0.592 | 319 | 0.119 |
| state including replay | 191 | 342.632 | 191 | 2.321 |
| context and rows | 65 | 217.021 | 65 | 2.374 |
| predictions | 65 | 4.207 | 65 | 3.892 |
| situation candidates | 65 | 0.903 | 65 | 0.900 |
| apply and validate | 6048 | 144.651 | 126 | 2.966 |

Raw per-edit results: [before](reports/b71_apf6/before.json),
[identical after](reports/b71_apf6/after-final.json),
[varied Confirm plus shell reset](reports/b71_apf6/confirm-varied-shell-final.json),
[bulk](reports/b71_apf6/bulk-varied.json). Earlier measurements are retained too.

## Design and check preservation

- `book_content.BookSourceCache` scopes source data to the resolved index path.
  File identities include path, size, nanosecond mtime, ctime and inode; the index
  and compressed resource spans have SHA-256 identities. Unchanged file identities
  need only stat calls. When a pack changes, only its named resource spans are
  hashed, and unchanged spans keep their parsed values. No multi-GB pack is hashed
  on every edit. Missing/replaced files invalidate reuse; a source changing during
  a resource read is refused. Reads still bind book names to filename IDs.
- `Backend` retains parsed source books, MASTER inventory and ROST, and reuses
  unchanged compiled Fine-tune books. `PlayCallingService` caches the source and
  non-CPU dependencies, digest-checked recipe files, immutable parsed staged books,
  and up to 64 validated ledger prefixes. A warm single CPU edit neither reloads
  the catalog nor replays earlier receipts. Undo reuses an existing valid prefix.
- Changed source/Fine-tune dependencies invalidate the base. Up to 128 cached
  writer transitions retain the exact consumed book/master/roster/mask inputs,
  authored request and returned facts. Replay revalidates only affected rows;
  ownership and scheme plans always replay their archive-dependent checks. Tests
  change one source book while retaining another book's validated receipt.
  Public state returns copy mutable book/mask dictionaries. Recipe schema/size,
  digest and before/after checks still run at their existing boundaries.
- `context` reads ratings, personnel and plays from one parsed book instead of
  reparsing that book for every play. Predictions retain the existing book,
  MASTER, tendency, side, situations and mask cache keys and unchanged arithmetic.
- `confirm_playcalling` holds the existing session lock. `confirm` calls the
  original `review(session, request, state=...)` with exactly the captured request
  and the current proposed state. `review` still calls `apply`, all original
  writers, MASTER verification, category/row coverage and the original refusal
  logic. The optional state argument is the earlier accepted pending changes;
  it has no separate replacement validation implementation. Tests compare direct
  review inputs and receipts to Confirm for every ordinary control, masks,
  MASTER rows/roles and ownership. Real scheme/retirement and build tests remain.
- Bulk reviews every row, including detected conflicts, collecting all errors.
  Removed-formation references conflict in either order, including donor references.
  Two individually valid removals cannot jointly empty required personnel rows.
  Final coverage is checked again after later MASTER changes. Blockers propagate
  to the same book and dependent donor additions; shared MASTER/ownership plans
  retain their whole batch. Retirement retains its paired team run share when
  refused, including a USER/donor book independent of the team assignment. Independent clean edits are replayed against the retained clean set
  before one payload store, one Undo snapshot and one modification-map assignment.
  Failed writes leave the project and Undo unchanged; save/reopen reparses receipts.
- The page uses **Confirm …** for direct actions and **Add … to pending** in queue
  mode. Live masks can be queued with their enable switch. Requests keep their
  selected book/team/row when browsing another book. **Show review details** is
  collapsible and optional; combined blockers stay inline outside it. Own-book
  planning and confirmation share one worker, avoiding a nested blocking worker.
  The existing theme, tooltips and accessibility descriptions are retained.
  The queue holds drafts for the open session; confirm before saving the project.
  The existing recipe bounds (4096 receipts and 2 MiB) are retained.

The [synthetic themed screenshot](reports/b71_apf6/pending-edits.png) shows two
formation blockers and the independently staged tendency. Blocker text wraps
inside the table, and clearing targets the logical row even under theme sorting.
The final Qt test covers the table width, row wrapping, automatic review,
synchronous shell refresh, mixed queue, source-session reset and write failure.

## Registry, packaging and boundaries

**Zero capability rows added: 176 total / 73 APF.** Existing CPU Play Calling
registry evidence names the two new suites, and existing CPU action bindings
include `confirm_playcalling`. The capability ID set is unchanged; its SHA-256
is `a5e791c1047da40e2d13827d93b97b9510de5676742e9777b0a049d2b274fa46`.
No count-pin, tuple, installer count or validation-plan count change is needed.
The registry edit is the user-requested evidence update to the existing row;
no protected 2K5 GUI, build, game-code, colour or scorebug file was changed.
The APF modules were already in the release allowlist; no new runtime module
or allowlist entry is needed.

Strict validation, provider integrity, product catalog, phase1 packaging, repin,
and a clean staged APF release/runtime check pass. Repin changes zero hashes.
The clean stage has **289 files**, imports **161 modules**, and reports **73 APF
capabilities**. Release checking finds no private/retail payload, symlink or
undeclared file. The installer test uses the prepared local interpreter with
source PYTHONPATH cleared; no network dependency install occurred.

The 75 inherited evidence paths and reviewed extractor files were restored or
verified through the prior hash-pinned hydration scripts, read-only from their
sources. Inventory files are independent copies. H7A remains mode 0755.
The private git directory, stage, test interpreter and bundle stay below the
200 MiB scratch limit; the temporary stage/interpreter are removed at delivery.

**PROVED:** measured source/ledger work reduction on the owned export; existing
reviews on the Confirm path; conflict/refusal checks; atomic clean-set staging;
Undo/save/reopen; offscreen page behavior; and the passing offline gates listed
above, subject to each test's stated native/synthetic boundary.

**UNWITNESSED:** actual gameplay, Xenia consumption of any staged data/patch,
Windows/macOS timing and rendering, the historic exact 63-edit session, and a
human editing session in the released installer. This job changes no gameplay
patch bytes and does not replace the APF-2/4/5 witness boundaries. No emulator
was opened. Re-test ordinary personnel, masks, requested rows and fourth-down
behavior in a real match using the integrated stack's existing witness procedure.

### Explicit skips

- `tests/mod_editor/test_apf_b661_ladder.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_b661_ladder.log).
- `tests/mod_editor/test_apf_b67_static_audit.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_b67_static_audit.log).
- `tests/mod_editor/test_apf_b67_writers_native.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_b67_writers_native.log).
- `tests/mod_editor/test_apf_b69_control_audit.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_b69_control_audit.log).
- `tests/mod_editor/test_apf_book_unlock_retail.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_book_unlock_retail.log).
- `tests/mod_editor/test_apf_defense_research_native.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_defense_research_native.log).
- `tests/mod_editor/test_apf_endzone_dxt5a.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_endzone_dxt5a.log).
- `tests/mod_editor/test_apf_field_art_patch.py`: 2 explicit skips; [full output](reports/b71_apf6/test_apf_field_art_patch.log).
- `tests/mod_editor/test_apf_splb_tag_reassignment.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_splb_tag_reassignment.log).
- `tests/mod_editor/test_apf_stfs_roster_rehash.py`: 1 explicit skips; [full output](reports/b71_apf6/test_apf_stfs_roster_rehash.log).

## Failures and retained history

The first development Qt expectations assumed a separate Review click and a
retirement receipt without its captured tendency. Those expectations now test
automatic confirmation or explicit queue mode. The first new fixture used a
nonexistent synthetic play ID and assumed the fake remover supplied MASTER;
both fixture assumptions were corrected. The inherited scheme Qt file first
failed its old Review expectation; its complete corrected run passes and still
checks the full scheme detail table, CSV, Undo and 5-2 control. Earlier failed
logs remain in the ledger. A baseline launcher whose short parent exited produced
no acceptance result; the supervised detached run supplies the reported baseline.
The batch coordinator may retain exit 1 from an earlier failed suite; acceptance
uses the latest complete standalone file run, never selected passing test cases.

## Retest and delivery

1. Open CPU Play Calling on the same export; choose O-ManBlock, USER-O and USER-D.
   Confirm play/formation ratings and audibles without a Review click. Check that
   controls stay available after completion and confirm the timings on the target OS.
2. Enable **Add edits to Pending edits**. Queue personnel, retirement with run/pass
   share, Never call, tendencies, audibles, requested rows and masks across books.
   Confirm all; verify clean edits appear together and one Undo restores them.
3. Queue removal plus a reference to that formation in either order, and two edits
   that jointly empty a personnel category. Every blocker should remain visible.
   Clear the conflicting row and confirm again. Retain the MASTER warning.
4. Save, reopen, build a copied game and inspect the existing writer receipts.
   Install masks separately when intended; pending drafts must first be confirmed.
   Gameplay and native Windows/macOS performance need their own witness.
5. Import the private bundle onto A7 `cea8a3c85db408dafeea15b361faee9d05be33a7`. Read the explicit paths and the
   final delivery receipt before integration; no push was performed.

Implementation commits before this report:

```
b752f5eb APF: retain dependent drafts and render complete automatic review details
9619e2ed APF: cache play-calling edits and confirm pending changes atomically
```

The final report commit, bundle SHA-256, bundle verification and cleanup commands
are recorded in `.scratch/astra-b71-apf6-delivery.json`, outside the report commit
to avoid a self-referential commit hash/timing. `ASTRA_LAST_MESSAGE.md` ends in
`ASTRA_DONE`.

## Command ledger

[commands.jsonl](reports/b71_apf6/commands.jsonl) records exact argv, UTC start,
wall seconds, exit and complete output for every formal profile, suite, gate,
hydration and implementation-commit command. The table includes failed attempts.
Read-only discovery, source inspection and editor tool calls are exploratory;
the session transcript retains those calls and tool-return timing, not test claims.
Detached work uses a separate process session with a waiting supervisor; no
name-based process killing was used. Final delivery commands use the separate
receipt described above.

| UTC start | Seconds | Exit | Command | Output |
| --- | ---: | ---: | --- | --- |
| 2026-09-16T06:20:41.415264+00:00 | 0.285 | 0 | `python3 reports/b71_apf3/prepare_test_python.py` | [log](reports/b71_apf6/prepare-python.log) |
| 2026-09-16T06:20:41.731136+00:00 | 0.044 | 0 | `python3 reports/b71_apf4/hydrate.py` | [log](reports/b71_apf6/hydrate.log) |
| 2026-09-16T06:20:41.826247+00:00 | 0.047 | 0 | `python3 reports/b71_apf2/hydrate_tools.py` | [log](reports/b71_apf6/hydrate-tools.log) |
| 2026-09-16T06:23:50.925524+00:00 | 459.503 | 0 | `python3 reports/b71_apf6/profile.py before` | [log](reports/b71_apf6/profile-before.log) |
| 2026-09-16T06:25:03.953370+00:00 | 1.464 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_facade.py` | [log](reports/b71_apf6/facade-first.log) |
| 2026-09-16T06:26:59.380619+00:00 | 4.782 | 1 | `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [log](reports/b71_apf6/qt-first.log) |
| 2026-09-16T06:27:25.278202+00:00 | 14.854 | 0 | `python3 reports/b71_apf6/profile.py after-first` | [log](reports/b71_apf6/profile-after-first.log) |
| 2026-09-16T06:29:45.737504+00:00 | 1.517 | 1 | `python3 tests/mod_editor/test_apf_b71_editor_workflow.py` | [log](reports/b71_apf6/workflow-first.log) |
| 2026-09-16T06:31:44.891101+00:00 | 2.320 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow.py` | [log](reports/b71_apf6/workflow-second.log) |
| 2026-09-16T06:32:55.959616+00:00 | 1.994 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/workflow-qt-first.log) |
| 2026-09-16T06:32:57.986126+00:00 | 5.294 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [log](reports/b71_apf6/qt-second.log) |
| 2026-09-16T06:33:43.059801+00:00 | 14.826 | 0 | `python3 reports/b71_apf6/profile.py after` | [log](reports/b71_apf6/profile-after.log) |
| 2026-09-16T06:33:57.917391+00:00 | 17.791 | 0 | `python3 reports/b71_apf6/profile.py confirm-varied` | [log](reports/b71_apf6/profile-confirm-varied.log) |
| 2026-09-16T06:34:25.004695+00:00 | 10.480 | 0 | `python3 packaging/repin.py --apply` | [log](reports/b71_apf6/repin-first.log) |
| 2026-09-16T06:35:05.551827+00:00 | 1520.274 | 1 | `.scratch/test-python/bin/python3 reports/b71_apf6/suites.py` | [log](reports/b71_apf6/suites.log) |
| 2026-09-16T06:35:05.615825+00:00 | 1.211 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf2k8_coverage_tuning.py` | [log](reports/b71_apf6/test_apf2k8_coverage_tuning.log) |
| 2026-09-16T06:35:05.617508+00:00 | 0.958 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_all_crest_slots.py` | [log](reports/b71_apf6/test_apf_all_crest_slots.log) |
| 2026-09-16T06:35:05.618112+00:00 | 0.352 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_annotation_facade.py` | [log](reports/b71_apf6/test_apf_audio_annotation_facade.log) |
| 2026-09-16T06:35:05.619608+00:00 | 0.460 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf2k8_playbook_route_writer.py` | [log](reports/b71_apf6/test_apf2k8_playbook_route_writer.log) |
| 2026-09-16T06:35:06.003767+00:00 | 0.304 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_annotations.py` | [log](reports/b71_apf6/test_apf_audio_annotations.log) |
| 2026-09-16T06:35:06.110053+00:00 | 0.184 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_batch_export.py` | [log](reports/b71_apf6/test_apf_audio_batch_export.log) |
| 2026-09-16T06:35:06.329748+00:00 | 0.319 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_batch_facade.py` | [log](reports/b71_apf6/test_apf_audio_batch_facade.log) |
| 2026-09-16T06:35:06.342094+00:00 | 0.770 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_batch_gui.py` | [log](reports/b71_apf6/test_apf_audio_batch_gui.log) |
| 2026-09-16T06:35:06.608404+00:00 | 2.001 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_decode_cancellation.py` | [log](reports/b71_apf6/test_apf_audio_decode_cancellation.log) |
| 2026-09-16T06:35:06.682582+00:00 | 0.665 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_drop_zone_gui.py` | [log](reports/b71_apf6/test_apf_audio_drop_zone_gui.log) |
| 2026-09-16T06:35:06.859764+00:00 | 0.643 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_encoder_gui.py` | [log](reports/b71_apf6/test_apf_audio_encoder_gui.log) |
| 2026-09-16T06:35:07.145647+00:00 | 11.455 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_encoding.py` | [log](reports/b71_apf6/test_apf_audio_encoding.log) |
| 2026-09-16T06:35:07.380407+00:00 | 3.942 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_import_idle_barrier.py` | [log](reports/b71_apf6/test_apf_audio_import_idle_barrier.log) |
| 2026-09-16T06:35:07.536123+00:00 | 1.051 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_pcm_product_backend.py` | [log](reports/b71_apf6/test_apf_audio_pcm_product_backend.log) |
| 2026-09-16T06:35:08.621428+00:00 | 0.668 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_replacement_pack.py` | [log](reports/b71_apf6/test_apf_audio_replacement_pack.log) |
| 2026-09-16T06:35:08.641137+00:00 | 0.613 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audio_waveform_qt.py` | [log](reports/b71_apf6/test_apf_audio_waveform_qt.log) |
| 2026-09-16T06:35:09.289716+00:00 | 0.251 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audo_exact_slot.py` | [log](reports/b71_apf6/test_apf_audo_exact_slot.log) |
| 2026-09-16T06:35:09.325427+00:00 | 0.320 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audo_product_backend.py` | [log](reports/b71_apf6/test_apf_audo_product_backend.log) |
| 2026-09-16T06:35:09.570464+00:00 | 0.180 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_audo_project.py` | [log](reports/b71_apf6/test_apf_audo_project.log) |
| 2026-09-16T06:35:09.680262+00:00 | 12.466 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ausb_exact_slot.py` | [log](reports/b71_apf6/test_apf_ausb_exact_slot.log) |
| 2026-09-16T06:35:09.779242+00:00 | 0.320 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ausb_product_backend.py` | [log](reports/b71_apf6/test_apf_ausb_product_backend.log) |
| 2026-09-16T06:35:10.132725+00:00 | 28.914 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b661_book_content.py` | [log](reports/b71_apf6/test_apf_b661_book_content.log) |
| 2026-09-16T06:35:11.355421+00:00 | 0.421 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b661_ladder.py` | [log](reports/b71_apf6/test_apf_b661_ladder.log) |
| 2026-09-16T06:35:11.810287+00:00 | 2.647 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b66_appearance.py` | [log](reports/b71_apf6/test_apf_b66_appearance.log) |
| 2026-09-16T06:35:14.492359+00:00 | 5.267 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b66_personnel.py` | [log](reports/b71_apf6/test_apf_b66_personnel.log) |
| 2026-09-16T06:35:18.630835+00:00 | 70.093 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_books_qt.py` | [log](reports/b71_apf6/test_apf_b67_books_qt.log) |
| 2026-09-16T06:35:19.792980+00:00 | 41.071 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_clone.py` | [log](reports/b71_apf6/test_apf_b67_clone.log) |
| 2026-09-16T06:35:22.183510+00:00 | 154.604 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_defense_model_native.py` | [log](reports/b71_apf6/test_apf_b67_defense_model_native.log) |
| 2026-09-16T06:35:39.080252+00:00 | 92.826 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_model_edges_native.py` | [log](reports/b71_apf6/test_apf_b67_model_edges_native.log) |
| 2026-09-16T06:36:00.896151+00:00 | 1246.566 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_model_native.py` | [log](reports/b71_apf6/test_apf_b67_model_native.log) |
| 2026-09-16T06:36:28.755314+00:00 | 0.130 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_static_audit.py` | [log](reports/b71_apf6/test_apf_b67_static_audit.log) |
| 2026-09-16T06:36:28.884477+00:00 | 2.330 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow.py` | [log](reports/b71_apf6/workflow-transitions.log) |
| 2026-09-16T06:36:28.915023+00:00 | 0.404 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_writers.py` | [log](reports/b71_apf6/test_apf_b67_writers.log) |
| 2026-09-16T06:36:29.353698+00:00 | 325.488 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_writers_native.py` | [log](reports/b71_apf6/test_apf_b67_writers_native.log) |
| 2026-09-16T06:36:31.247692+00:00 | 4.117 | 0 | `python3 tests/mod_editor/test_apf_b71_situations.py` | [log](reports/b71_apf6/rebase-transitions.log) |
| 2026-09-16T06:36:58.102368+00:00 | 11.039 | 0 | `python3 packaging/repin.py --apply` | [log](reports/b71_apf6/repin-implementation.log) |
| 2026-09-16T06:37:09.169989+00:00 | 0.154 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [log](reports/b71_apf6/strict-registry-first.log) |
| 2026-09-16T06:37:11.936909+00:00 | 0.267 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b67_xenia_patch.py` | [log](reports/b71_apf6/test_apf_b67_xenia_patch.log) |
| 2026-09-16T06:37:12.237856+00:00 | 29.858 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_build.py` | [log](reports/b71_apf6/test_apf_b69_build.log) |
| 2026-09-16T06:37:28.847364+00:00 | 0.037 | 0 | `git --git-dir=.scratch/git --work-tree=. add -f -- mod_editor/apf_studio/book_content.py mod_editor/apf_studio/facade.py mod_editor/apf_studio/playcalling_service.py mod_editor/apf_studio/playcalling_editor_qt.py mod_editor/apf_studio/situation_mask_qt.py mod_editor/capabilities/registry.v1.json docs/mod_editor/apf_b67_play_calling_editor.md docs/mod_editor/apf2k8_mod_studio_changelog.md tests/mod_editor/test_apf_playcalling_editor_qt.py tests/mod_editor/test_apf_b71_editor_workflow.py tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/add-implementation.log) |
| 2026-09-16T06:37:28.913731+00:00 | 0.020 | 0 | `git --git-dir=.scratch/git --work-tree=. diff --cached --check` | [log](reports/b71_apf6/diff-implementation.log) |
| 2026-09-16T06:37:28.964613+00:00 | 0.060 | 0 | `git --git-dir=.scratch/git --work-tree=. commit -m 'APF: cache play-calling edits and confirm pending changes atomically' -- mod_editor/apf_studio/book_content.py mod_editor/apf_studio/facade.py mod_editor/apf_studio/playcalling_service.py mod_editor/apf_studio/playcalling_editor_qt.py mod_editor/apf_studio/situation_mask_qt.py mod_editor/capabilities/registry.v1.json docs/mod_editor/apf_b67_play_calling_editor.md docs/mod_editor/apf2k8_mod_studio_changelog.md tests/mod_editor/test_apf_playcalling_editor_qt.py tests/mod_editor/test_apf_b71_editor_workflow.py tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/commit-implementation.log) |
| 2026-09-16T06:37:42.127754+00:00 | 0.101 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_control_audit.py` | [log](reports/b71_apf6/test_apf_b69_control_audit.log) |
| 2026-09-16T06:37:42.258928+00:00 | 79.219 | 1 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_editor_qt.py` | [log](reports/b71_apf6/test_apf_b69_editor_qt.log) |
| 2026-09-16T06:37:56.821823+00:00 | 0.454 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_formation_calling.py` | [log](reports/b71_apf6/test_apf_b69_formation_calling.log) |
| 2026-09-16T06:37:57.308555+00:00 | 0.392 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_launch_patches.py` | [log](reports/b71_apf6/test_apf_b69_launch_patches.log) |
| 2026-09-16T06:37:57.733664+00:00 | 827.638 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_native.py` | [log](reports/b71_apf6/test_apf_b69_native.log) |
| 2026-09-16T06:38:33.061484+00:00 | 2.507 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow.py` | [log](reports/b71_apf6/workflow-dependencies.log) |
| 2026-09-16T06:39:01.513089+00:00 | 148.550 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_retirement_native.py` | [log](reports/b71_apf6/test_apf_b69_retirement_native.log) |
| 2026-09-16T06:39:21.713012+00:00 | 0.086 | 0 | `python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt .scratch/apf-release` | [log](reports/b71_apf6/release-stage.log) |
| 2026-09-16T06:39:21.829316+00:00 | 0.390 | 0 | `env PYTHONDONTWRITEBYTECODE=1 python3 packaging/check_apf2k8_mod_studio_release.py .scratch/apf-release` | [log](reports/b71_apf6/release-check.log) |
| 2026-09-16T06:39:22.249607+00:00 | 10.442 | 0 | `env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/home/noah/2k-worktrees/astra-b71-apf6/.scratch/apf-release .scratch/test-python/bin/python3 .scratch/apf-release/packaging/check_apf2k8_mod_studio_runtime.py` | [log](reports/b71_apf6/release-runtime.log) |
| 2026-09-16T06:41:11.379239+00:00 | 2.036 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/final-workflow-qt.log) |
| 2026-09-16T06:41:13.449399+00:00 | 81.861 | 0 | `python3 tests/mod_editor/test_apf_b69_editor_qt.py` | [log](reports/b71_apf6/final-b69-editor.log) |
| 2026-09-16T06:41:30.095275+00:00 | 39.689 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_schemes.py` | [log](reports/b71_apf6/test_apf_b69_schemes.log) |
| 2026-09-16T06:41:39.278512+00:00 | 14.760 | 0 | `python3 reports/b71_apf6/profile.py after-final` | [log](reports/b71_apf6/profile-after-final.log) |
| 2026-09-16T06:41:54.067780+00:00 | 20.118 | 0 | `python3 reports/b71_apf6/profile.py confirm-varied-shell-final` | [log](reports/b71_apf6/profile-confirm-varied-shell-final.log) |
| 2026-09-16T06:41:54.875366+00:00 | 0.394 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b69_wiring.py` | [log](reports/b71_apf6/test_apf_b69_wiring.log) |
| 2026-09-16T06:41:55.302550+00:00 | 200.961 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b70_stock_recipes.py` | [log](reports/b71_apf6/test_apf_b70_stock_recipes.log) |
| 2026-09-16T06:42:09.818182+00:00 | 2.595 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_editor_workflow.py` | [log](reports/b71_apf6/test_apf_b71_editor_workflow.log) |
| 2026-09-16T06:42:12.446551+00:00 | 2.043 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/test_apf_b71_editor_workflow_qt.log) |
| 2026-09-16T06:42:14.522837+00:00 | 2.846 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask.py` | [log](reports/b71_apf6/test_apf_b71_situation_mask.log) |
| 2026-09-16T06:42:17.401725+00:00 | 4.307 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask_abi.py` | [log](reports/b71_apf6/test_apf_b71_situation_mask_abi.log) |
| 2026-09-16T06:42:21.738819+00:00 | 1.260 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask_install.py` | [log](reports/b71_apf6/test_apf_b71_situation_mask_install.log) |
| 2026-09-16T06:42:23.028873+00:00 | 359.486 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask_native.py` | [log](reports/b71_apf6/test_apf_b71_situation_mask_native.log) |
| 2026-09-16T06:42:35.343230+00:00 | 5.361 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [log](reports/b71_apf6/final-playcalling-qt.log) |
| 2026-09-16T06:42:45.594431+00:00 | 0.872 | 0 | `python3 reports/b71_apf6/queue_snapshot.py` | [log](reports/b71_apf6/queue-snapshot.log) |
| 2026-09-16T06:43:56.269022+00:00 | 2.067 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/queue-layout.log) |
| 2026-09-16T06:43:58.368254+00:00 | 0.864 | 0 | `python3 reports/b71_apf6/queue_snapshot.py` | [log](reports/b71_apf6/queue-snapshot-final.log) |
| 2026-09-16T06:45:16.294641+00:00 | 1.400 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situation_mask_qt.py` | [log](reports/b71_apf6/test_apf_b71_situation_mask_qt.log) |
| 2026-09-16T06:45:17.727373+00:00 | 4.156 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_b71_situations.py` | [log](reports/b71_apf6/test_apf_b71_situations.log) |
| 2026-09-16T06:45:21.917100+00:00 | 0.251 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_book_identity_qt.py` | [log](reports/b71_apf6/test_apf_book_identity_qt.log) |
| 2026-09-16T06:45:22.200683+00:00 | 25.552 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_book_unlock.py` | [log](reports/b71_apf6/test_apf_book_unlock.log) |
| 2026-09-16T06:45:22.635159+00:00 | 3.036 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/queue-layout-wrap.log) |
| 2026-09-16T06:45:25.702616+00:00 | 0.853 | 0 | `python3 reports/b71_apf6/queue_snapshot.py` | [log](reports/b71_apf6/queue-snapshot-wrap.log) |
| 2026-09-16T06:45:47.787111+00:00 | 0.146 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_book_unlock_retail.py` | [log](reports/b71_apf6/test_apf_book_unlock_retail.log) |
| 2026-09-16T06:45:47.962984+00:00 | 0.837 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_browser_workspace_handoff.py` | [log](reports/b71_apf6/test_apf_browser_workspace_handoff.log) |
| 2026-09-16T06:45:48.829754+00:00 | 0.303 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_build_ausb_overlays.py` | [log](reports/b71_apf6/test_apf_build_ausb_overlays.log) |
| 2026-09-16T06:45:49.165596+00:00 | 0.306 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_build_raw_span_overlays.py` | [log](reports/b71_apf6/test_apf_build_raw_span_overlays.log) |
| 2026-09-16T06:45:49.505009+00:00 | 0.441 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_capability_action_parity.py` | [log](reports/b71_apf6/test_apf_capability_action_parity.log) |
| 2026-09-16T06:45:49.981470+00:00 | 0.293 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_copied_volume_metadata.py` | [log](reports/b71_apf6/test_apf_copied_volume_metadata.log) |
| 2026-09-16T06:45:50.308297+00:00 | 0.072 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_coverage_research_tools.py` | [log](reports/b71_apf6/test_apf_coverage_research_tools.log) |
| 2026-09-16T06:45:50.416578+00:00 | 2.873 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_cpu_audibles.py` | [log](reports/b71_apf6/test_apf_cpu_audibles.log) |
| 2026-09-16T06:45:52.571213+00:00 | 8.351 | 0 | `python3 reports/b71_apf6/profile.py bulk-varied` | [log](reports/b71_apf6/profile-bulk.log) |
| 2026-09-16T06:45:53.324171+00:00 | 0.824 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_crest_budget_import.py` | [log](reports/b71_apf6/test_apf_crest_budget_import.log) |
| 2026-09-16T06:45:54.182643+00:00 | 28.116 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_crest_fit.py` | [log](reports/b71_apf6/test_apf_crest_fit.log) |
| 2026-09-16T06:46:22.331003+00:00 | 0.319 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_cross_domain_audio_safety.py` | [log](reports/b71_apf6/test_apf_cross_domain_audio_safety.log) |
| 2026-09-16T06:46:22.679564+00:00 | 21.383 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_cubemap_face0_preview.py` | [log](reports/b71_apf6/test_apf_cubemap_face0_preview.log) |
| 2026-09-16T06:46:44.095931+00:00 | 0.324 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_custom_team_appearance_gui.py` | [log](reports/b71_apf6/test_apf_custom_team_appearance_gui.log) |
| 2026-09-16T06:46:44.453421+00:00 | 6.996 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_custom_team_appearance_patch.py` | [log](reports/b71_apf6/test_apf_custom_team_appearance_patch.log) |
| 2026-09-16T06:46:45.178846+00:00 | 2.591 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow.py` | [log](reports/b71_apf6/final-workflow.log) |
| 2026-09-16T06:46:47.800554+00:00 | 1.435 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_facade.py` | [log](reports/b71_apf6/final-facade.log) |
| 2026-09-16T06:46:49.268967+00:00 | 5.357 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [log](reports/b71_apf6/final-qt-after-layout.log) |
| 2026-09-16T06:46:51.485505+00:00 | 0.514 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_defense_research_identity.py` | [log](reports/b71_apf6/test_apf_defense_research_identity.log) |
| 2026-09-16T06:46:52.030379+00:00 | 139.973 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_defense_research_native.py` | [log](reports/b71_apf6/test_apf_defense_research_native.log) |
| 2026-09-16T06:46:54.658959+00:00 | 0.155 | 0 | `python3 tests/mod_editor/test_product_catalog.py` | [log](reports/b71_apf6/product-catalog-final.log) |
| 2026-09-16T06:46:54.844167+00:00 | 2.131 | 0 | `python3 tests/mod_editor/test_phase1_packaging.py` | [log](reports/b71_apf6/phase1-final.log) |
| 2026-09-16T06:46:57.008129+00:00 | 9.923 | 0 | `python3 tests/mod_editor/test_provider_integrity.py` | [log](reports/b71_apf6/provider-integrity-final.log) |
| 2026-09-16T06:47:44.433375+00:00 | 22.710 | 0 | `python3 reports/b71_apf6/final_gates.py` | [log](reports/b71_apf6/final-gates.log) |
| 2026-09-16T06:47:44.495365+00:00 | 11.321 | 0 | `python3 packaging/repin.py --apply` | [log](reports/b71_apf6/repin-final.log) |
| 2026-09-16T06:47:55.847571+00:00 | 0.156 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [log](reports/b71_apf6/strict-registry-final.log) |
| 2026-09-16T06:47:56.032803+00:00 | 0.063 | 0 | `python3 reports/b71_apf6/audit_delivery.py` | [log](reports/b71_apf6/delivery-audit.log) |
| 2026-09-16T06:47:56.125458+00:00 | 0.089 | 0 | `python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt .scratch/apf-release` | [log](reports/b71_apf6/release-stage-final.log) |
| 2026-09-16T06:47:56.246562+00:00 | 0.385 | 0 | `env PYTHONDONTWRITEBYTECODE=1 python3 packaging/check_apf2k8_mod_studio_release.py .scratch/apf-release` | [log](reports/b71_apf6/release-check-final.log) |
| 2026-09-16T06:47:56.660845+00:00 | 10.469 | 0 | `env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/home/noah/2k-worktrees/astra-b71-apf6/.scratch/apf-release .scratch/test-python/bin/python3 .scratch/apf-release/packaging/check_apf2k8_mod_studio_runtime.py` | [log](reports/b71_apf6/release-runtime-final.log) |
| 2026-09-16T06:48:22.547947+00:00 | 0.334 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_digital_font.py` | [log](reports/b71_apf6/test_apf_digital_font.log) |
| 2026-09-16T06:48:22.916345+00:00 | 13.010 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_dxn_base_only_namefont.py` | [log](reports/b71_apf6/test_apf_dxn_base_only_namefont.log) |
| 2026-09-16T06:48:35.965048+00:00 | 21.069 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_dxt5a_general_preview.py` | [log](reports/b71_apf6/test_apf_dxt5a_general_preview.log) |
| 2026-09-16T06:48:36.388822+00:00 | 0.019 | 0 | `git --git-dir=.scratch/git --work-tree=. add -f -- docs/mod_editor/apf2k8_mod_studio_changelog.md docs/mod_editor/apf_b67_play_calling_editor.md mod_editor/apf_studio/book_content.py mod_editor/apf_studio/facade.py mod_editor/apf_studio/models.py mod_editor/apf_studio/playcalling_editor_qt.py mod_editor/apf_studio/playcalling_service.py mod_editor/apf_studio/situation_mask_qt.py mod_editor/capabilities/registry.v1.json tests/mod_editor/test_apf_b69_editor_qt.py tests/mod_editor/test_apf_b71_editor_workflow.py tests/mod_editor/test_apf_b71_editor_workflow_qt.py tests/mod_editor/test_apf_playcalling_editor_qt.py` | [log](reports/b71_apf6/add-refinements.log) |
| 2026-09-16T06:48:36.438506+00:00 | 0.009 | 0 | `git --git-dir=.scratch/git --work-tree=. diff --cached --check` | [log](reports/b71_apf6/diff-refinements.log) |
| 2026-09-16T06:48:36.475820+00:00 | 10.544 | 0 | `python3 packaging/repin.py --apply` | [log](reports/b71_apf6/repin-before-refinements.log) |
| 2026-09-16T06:48:47.048908+00:00 | 0.045 | 0 | `git --git-dir=.scratch/git --work-tree=. commit -m 'APF: retain dependent drafts and render complete automatic review details' -- docs/mod_editor/apf2k8_mod_studio_changelog.md docs/mod_editor/apf_b67_play_calling_editor.md mod_editor/apf_studio/book_content.py mod_editor/apf_studio/facade.py mod_editor/apf_studio/models.py mod_editor/apf_studio/playcalling_editor_qt.py mod_editor/apf_studio/playcalling_service.py mod_editor/apf_studio/situation_mask_qt.py mod_editor/capabilities/registry.v1.json tests/mod_editor/test_apf_b69_editor_qt.py tests/mod_editor/test_apf_b71_editor_workflow.py tests/mod_editor/test_apf_b71_editor_workflow_qt.py tests/mod_editor/test_apf_playcalling_editor_qt.py` | [log](reports/b71_apf6/commit-refinements.log) |
| 2026-09-16T06:48:57.068212+00:00 | 38.684 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_endzone_dxt5a.py` | [log](reports/b71_apf6/test_apf_endzone_dxt5a.log) |
| 2026-09-16T06:49:12.035571+00:00 | 0.126 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_export.py` | [log](reports/b71_apf6/test_apf_export.log) |
| 2026-09-16T06:49:12.195436+00:00 | 0.343 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_external_audio_bank_bundle.py` | [log](reports/b71_apf6/test_apf_external_audio_bank_bundle.log) |
| 2026-09-16T06:49:12.572611+00:00 | 0.186 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_art.py` | [log](reports/b71_apf6/test_apf_field_art.log) |
| 2026-09-16T06:49:12.791987+00:00 | 0.866 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_art_gui.py` | [log](reports/b71_apf6/test_apf_field_art_gui.log) |
| 2026-09-16T06:49:13.691352+00:00 | 298.499 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_art_patch.py` | [log](reports/b71_apf6/test_apf_field_art_patch.log) |
| 2026-09-16T06:49:35.784881+00:00 | 0.473 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_art_stock_label.py` | [log](reports/b71_apf6/test_apf_field_art_stock_label.log) |
| 2026-09-16T06:49:36.289550+00:00 | 204.882 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_extra_roundtrip.py` | [log](reports/b71_apf6/test_apf_field_extra_roundtrip.log) |
| 2026-09-16T06:51:26.621379+00:00 | 2.963 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/final-queue-sorting.log) |
| 2026-09-16T06:51:45.407097+00:00 | 0.577 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_material_project.py` | [log](reports/b71_apf6/test_apf_field_material_project.log) |
| 2026-09-16T06:51:46.018304+00:00 | 0.334 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_field_material_writer.py` | [log](reports/b71_apf6/test_apf_field_material_writer.log) |
| 2026-09-16T06:51:46.389391+00:00 | 0.345 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_formation_alignment_writer.py` | [log](reports/b71_apf6/test_apf_formation_alignment_writer.log) |
| 2026-09-16T06:51:46.770034+00:00 | 0.211 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_fourth_down.py` | [log](reports/b71_apf6/test_apf_fourth_down.log) |
| 2026-09-16T06:51:47.011970+00:00 | 102.205 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_fourth_down_native.py` | [log](reports/b71_apf6/test_apf_fourth_down_native.log) |
| 2026-09-16T06:52:26.762880+00:00 | 0.053 | 0 | `python3 reports/b71_apf6/make_report.py` | [log](reports/b71_apf6/report-draft.log) |
| 2026-09-16T06:53:01.203182+00:00 | 0.185 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_fourth_down_qt.py` | [log](reports/b71_apf6/test_apf_fourth_down_qt.log) |
| 2026-09-16T06:53:01.420792+00:00 | 0.046 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_full_shell_visual_gate.py` | [log](reports/b71_apf6/test_apf_full_shell_visual_gate.log) |
| 2026-09-16T06:53:01.497072+00:00 | 0.518 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_g12_surfaces.py` | [log](reports/b71_apf6/test_apf_g12_surfaces.log) |
| 2026-09-16T06:53:02.045904+00:00 | 1.454 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_helmet_crest_design_product.py` | [log](reports/b71_apf6/test_apf_helmet_crest_design_product.log) |
| 2026-09-16T06:53:03.529638+00:00 | 7.397 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_helmet_logo_placement.py` | [log](reports/b71_apf6/test_apf_helmet_logo_placement.log) |
| 2026-09-16T06:53:10.960888+00:00 | 4.078 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_helmet_logo_regions.py` | [log](reports/b71_apf6/test_apf_helmet_logo_regions.log) |
| 2026-09-16T06:53:15.071860+00:00 | 1.217 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_helmet_logo_regions_qt.py` | [log](reports/b71_apf6/test_apf_helmet_logo_regions_qt.log) |
| 2026-09-16T06:53:16.321769+00:00 | 0.611 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_import_offers_resize.py` | [log](reports/b71_apf6/test_apf_import_offers_resize.log) |
| 2026-09-16T06:53:16.966766+00:00 | 0.207 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_iso_extraction_is_layout_tolerant.py` | [log](reports/b71_apf6/test_apf_iso_extraction_is_layout_tolerant.log) |
| 2026-09-16T06:53:17.206151+00:00 | 0.060 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_linear_txtr_png.py` | [log](reports/b71_apf6/test_apf_linear_txtr_png.log) |
| 2026-09-16T06:53:17.296634+00:00 | 13.697 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_logo_patch.py` | [log](reports/b71_apf6/test_apf_logo_patch.log) |
| 2026-09-16T06:53:29.252872+00:00 | 0.096 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_logo_surface_ownership.py` | [log](reports/b71_apf6/test_apf_logo_surface_ownership.log) |
| 2026-09-16T06:53:29.378849+00:00 | 43.635 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_logocache_patch.py` | [log](reports/b71_apf6/test_apf_logocache_patch.log) |
| 2026-09-16T06:53:31.026093+00:00 | 0.177 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_mask_preview_alpha.py` | [log](reports/b71_apf6/test_apf_mask_preview_alpha.log) |
| 2026-09-16T06:53:31.233485+00:00 | 2.677 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_model_export_gui.py` | [log](reports/b71_apf6/test_apf_model_export_gui.log) |
| 2026-09-16T06:53:33.943900+00:00 | 52.285 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_model_import.py` | [log](reports/b71_apf6/test_apf_model_import.log) |
| 2026-09-16T06:54:12.224442+00:00 | 2.172 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_number_encode_defaults.py` | [log](reports/b71_apf6/test_apf_number_encode_defaults.log) |
| 2026-09-16T06:54:13.044952+00:00 | 267.822 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_number_texture_writer.py` | [log](reports/b71_apf6/test_apf_number_texture_writer.log) |
| 2026-09-16T06:54:14.427198+00:00 | 1.320 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_package_map_writer.py` | [log](reports/b71_apf6/test_apf_package_map_writer.log) |
| 2026-09-16T06:54:15.780114+00:00 | 0.505 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_pass_fetch_export_qt.py` | [log](reports/b71_apf6/test_apf_pass_fetch_export_qt.log) |
| 2026-09-16T06:54:16.319159+00:00 | 13.160 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_play_designer.py` | [log](reports/b71_apf6/test_apf_play_designer.log) |
| 2026-09-16T06:54:26.264529+00:00 | 0.521 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_play_designer_project.py` | [log](reports/b71_apf6/test_apf_play_designer_project.log) |
| 2026-09-16T06:54:26.816595+00:00 | 0.335 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_play_designer_qt.py` | [log](reports/b71_apf6/test_apf_play_designer_qt.log) |
| 2026-09-16T06:54:27.187302+00:00 | 0.338 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playbook_route_gui.py` | [log](reports/b71_apf6/test_apf_playbook_route_gui.log) |
| 2026-09-16T06:54:27.560607+00:00 | 1.981 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcall_patch.py` | [log](reports/b71_apf6/test_apf_playcall_patch.log) |
| 2026-09-16T06:54:29.512338+00:00 | 220.934 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcall_research_native.py` | [log](reports/b71_apf6/test_apf_playcall_research_native.log) |
| 2026-09-16T06:54:29.577119+00:00 | 94.606 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcalling_editor_build.py` | [log](reports/b71_apf6/test_apf_playcalling_editor_build.log) |
| 2026-09-16T06:56:04.214869+00:00 | 1.383 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcalling_editor_facade.py` | [log](reports/b71_apf6/test_apf_playcalling_editor_facade.log) |
| 2026-09-16T06:56:05.631348+00:00 | 0.539 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcalling_editor_patches.py` | [log](reports/b71_apf6/test_apf_playcalling_editor_patches.log) |
| 2026-09-16T06:56:06.201523+00:00 | 5.452 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_playcalling_editor_qt.py` | [log](reports/b71_apf6/test_apf_playcalling_editor_qt.log) |
| 2026-09-16T06:56:11.688322+00:00 | 6.747 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_position_patch.py` | [log](reports/b71_apf6/test_apf_player_position_patch.log) |
| 2026-09-16T06:56:18.466580+00:00 | 20.365 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_position_product_backend.py` | [log](reports/b71_apf6/test_apf_player_position_product_backend.log) |
| 2026-09-16T06:56:38.865837+00:00 | 0.114 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_positions.py` | [log](reports/b71_apf6/test_apf_player_positions.log) |
| 2026-09-16T06:56:39.011548+00:00 | 4.161 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_rating_patch.py` | [log](reports/b71_apf6/test_apf_player_rating_patch.log) |
| 2026-09-16T06:56:43.206477+00:00 | 9.066 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_rating_product_backend.py` | [log](reports/b71_apf6/test_apf_player_rating_product_backend.log) |
| 2026-09-16T06:56:47.497304+00:00 | 15.015 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_rating_sheet_import.py` | [log](reports/b71_apf6/test_apf_player_rating_sheet_import.log) |
| 2026-09-16T06:56:52.308970+00:00 | 0.819 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_player_ratings.py` | [log](reports/b71_apf6/test_apf_player_ratings.log) |
| 2026-09-16T06:56:53.161221+00:00 | 0.158 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_product_findings.py` | [log](reports/b71_apf6/test_apf_product_findings.log) |
| 2026-09-16T06:56:53.353182+00:00 | 0.529 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_product_findings_gui.py` | [log](reports/b71_apf6/test_apf_product_findings_gui.log) |
| 2026-09-16T06:56:53.911284+00:00 | 0.232 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_product_validation_wrappers.py` | [log](reports/b71_apf6/test_apf_product_validation_wrappers.log) |
| 2026-09-16T06:56:54.177157+00:00 | 31.185 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_project_document_workflow.py` | [log](reports/b71_apf6/test_apf_project_document_workflow.log) |
| 2026-09-16T06:57:02.547153+00:00 | 0.199 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_project_streaming.py` | [log](reports/b71_apf6/test_apf_project_streaming.log) |
| 2026-09-16T06:57:02.778136+00:00 | 1.122 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_probes.py` | [log](reports/b71_apf6/test_apf_ps3_probes.log) |
| 2026-09-16T06:57:03.932851+00:00 | 16.632 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_roster_convert.py` | [log](reports/b71_apf6/test_apf_ps3_roster_convert.log) |
| 2026-09-16T06:57:20.600072+00:00 | 1.623 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_roster_import_qt.py` | [log](reports/b71_apf6/test_apf_ps3_roster_import_qt.log) |
| 2026-09-16T06:57:22.254033+00:00 | 3.836 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_speed.py` | [log](reports/b71_apf6/test_apf_ps3_speed.log) |
| 2026-09-16T06:57:25.396490+00:00 | 10.221 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_speed_packages.py` | [log](reports/b71_apf6/test_apf_ps3_speed_packages.log) |
| 2026-09-16T06:57:26.124897+00:00 | 29.823 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_texture_bundle.py` | [log](reports/b71_apf6/test_apf_ps3_texture_bundle.log) |
| 2026-09-16T06:57:35.653634+00:00 | 0.392 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_ps3_texture_bundle_qt.py` | [log](reports/b71_apf6/test_apf_ps3_texture_bundle_qt.log) |
| 2026-09-16T06:57:36.082854+00:00 | 0.155 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_public_docs_registry_current.py` | [log](reports/b71_apf6/test_apf_public_docs_registry_current.log) |
| 2026-09-16T06:57:36.268948+00:00 | 0.175 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_rating_value_domains.py` | [log](reports/b71_apf6/test_apf_rating_value_domains.log) |
| 2026-09-16T06:57:36.475525+00:00 | 0.043 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_retail_crest_channel_audit.py` | [log](reports/b71_apf6/test_apf_retail_crest_channel_audit.log) |
| 2026-09-16T06:57:36.549816+00:00 | 8.403 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_appearance_transfer.py` | [log](reports/b71_apf6/test_apf_roster_appearance_transfer.log) |
| 2026-09-16T06:57:44.987930+00:00 | 4.912 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_appearance_transfer_qt.py` | [log](reports/b71_apf6/test_apf_roster_appearance_transfer_qt.log) |
| 2026-09-16T06:57:49.933965+00:00 | 11.578 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_identity.py` | [log](reports/b71_apf6/test_apf_roster_identity.log) |
| 2026-09-16T06:57:55.982218+00:00 | 1.732 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_identity_gui.py` | [log](reports/b71_apf6/test_apf_roster_identity_gui.log) |
| 2026-09-16T06:57:57.748382+00:00 | 0.144 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_workspace.py` | [log](reports/b71_apf6/test_apf_roster_workspace.log) |
| 2026-09-16T06:57:57.926171+00:00 | 0.367 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_roster_workspace_gui.py` | [log](reports/b71_apf6/test_apf_roster_workspace_gui.log) |
| 2026-09-16T06:57:58.325062+00:00 | 1.280 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_save_playbook_assignments_gui.py` | [log](reports/b71_apf6/test_apf_save_playbook_assignments_gui.log) |
| 2026-09-16T06:57:59.641189+00:00 | 4.471 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_save_roster_players.py` | [log](reports/b71_apf6/test_apf_save_roster_players.log) |
| 2026-09-16T06:58:01.546642+00:00 | 0.734 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_save_roster_players_gui.py` | [log](reports/b71_apf6/test_apf_save_roster_players_gui.log) |
| 2026-09-16T06:58:02.315600+00:00 | 0.571 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_scorebug_workspace_qt.py` | [log](reports/b71_apf6/test_apf_scorebug_workspace_qt.log) |
| 2026-09-16T06:58:02.921991+00:00 | 11.103 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_shell_search_accessibility_qt.py` | [log](reports/b71_apf6/test_apf_shell_search_accessibility_qt.log) |
| 2026-09-16T06:58:04.146527+00:00 | 0.585 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_splb_add_multiple_formations.py` | [log](reports/b71_apf6/test_apf_splb_add_multiple_formations.log) |
| 2026-09-16T06:58:04.765257+00:00 | 1.104 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_splb_formation_personnel.py` | [log](reports/b71_apf6/test_apf_splb_formation_personnel.log) |
| 2026-09-16T06:58:05.906784+00:00 | 2.139 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_splb_tag_reassignment.py` | [log](reports/b71_apf6/test_apf_splb_tag_reassignment.log) |
| 2026-09-16T06:58:08.081125+00:00 | 0.361 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_splb_writer.py` | [log](reports/b71_apf6/test_apf_splb_writer.log) |
| 2026-09-16T06:58:08.476172+00:00 | 0.106 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_material_findings.py` | [log](reports/b71_apf6/test_apf_stadium_material_findings.log) |
| 2026-09-16T06:58:08.614970+00:00 | 0.276 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_model_import.py` | [log](reports/b71_apf6/test_apf_stadium_model_import.log) |
| 2026-09-16T06:58:08.922541+00:00 | 0.230 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_studio.py` | [log](reports/b71_apf6/test_apf_stadium_studio.log) |
| 2026-09-16T06:58:09.185802+00:00 | 0.541 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_studio_gui.py` | [log](reports/b71_apf6/test_apf_stadium_studio_gui.log) |
| 2026-09-16T06:58:09.761372+00:00 | 73.581 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stadium_texture.py` | [log](reports/b71_apf6/test_apf_stadium_texture.log) |
| 2026-09-16T06:58:10.482785+00:00 | 0.650 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_stfs_roster_rehash.py` | [log](reports/b71_apf6/test_apf_stfs_roster_rehash.log) |
| 2026-09-16T06:58:11.168372+00:00 | 1.141 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_audio_gui.py` | [log](reports/b71_apf6/test_apf_studio_audio_gui.log) |
| 2026-09-16T06:58:12.345425+00:00 | 0.250 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_core.py` | [log](reports/b71_apf6/test_apf_studio_core.log) |
| 2026-09-16T06:58:12.632064+00:00 | 0.540 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_draft_logo.py` | [log](reports/b71_apf6/test_apf_studio_draft_logo.log) |
| 2026-09-16T06:58:13.207848+00:00 | 2.344 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_inspectors.py` | [log](reports/b71_apf6/test_apf_studio_inspectors.log) |
| 2026-09-16T06:58:14.060759+00:00 | 14.607 | 0 | `env -u PYTHONPATH /home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_installer.py` | [log](reports/b71_apf6/test_apf_studio_installer.log) |
| 2026-09-16T06:58:15.587975+00:00 | 0.453 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_safety.py` | [log](reports/b71_apf6/test_apf_studio_safety.log) |
| 2026-09-16T06:58:16.076264+00:00 | 0.493 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_studio_text_edit.py` | [log](reports/b71_apf6/test_apf_studio_text_edit.log) |
| 2026-09-16T06:58:16.600597+00:00 | 9.862 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_team_art.py` | [log](reports/b71_apf6/test_apf_team_art.log) |
| 2026-09-16T06:58:26.495733+00:00 | 0.559 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_team_art_qt.py` | [log](reports/b71_apf6/test_apf_team_art_qt.log) |
| 2026-09-16T06:58:27.090386+00:00 | 0.622 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_team_crest_selection.py` | [log](reports/b71_apf6/test_apf_team_crest_selection.log) |
| 2026-09-16T06:58:27.746712+00:00 | 2.026 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_team_logo_gui.py` | [log](reports/b71_apf6/test_apf_team_logo_gui.log) |
| 2026-09-16T06:58:28.701142+00:00 | 0.528 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_text_sheet_gui.py` | [log](reports/b71_apf6/test_apf_text_sheet_gui.log) |
| 2026-09-16T06:58:29.262300+00:00 | 0.699 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_textlogo_gui.py` | [log](reports/b71_apf6/test_apf_textlogo_gui.log) |
| 2026-09-16T06:58:29.807080+00:00 | 60.224 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_textlogo_writer.py` | [log](reports/b71_apf6/test_apf_textlogo_writer.log) |
| 2026-09-16T06:58:29.991966+00:00 | 17.891 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_theme_layout_qt.py` | [log](reports/b71_apf6/test_apf_theme_layout_qt.log) |
| 2026-09-16T06:58:40.901496+00:00 | 1.386 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_allocation_capacity.py` | [log](reports/b71_apf6/test_apf_uniform_allocation_capacity.log) |
| 2026-09-16T06:58:42.321390+00:00 | 7.680 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_equipment_colors.py` | [log](reports/b71_apf6/test_apf_uniform_equipment_colors.log) |
| 2026-09-16T06:58:47.916788+00:00 | 0.197 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_equipment_colors_gui.py` | [log](reports/b71_apf6/test_apf_uniform_equipment_colors_gui.log) |
| 2026-09-16T06:58:48.147146+00:00 | 1.479 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_independence.py` | [log](reports/b71_apf6/test_apf_uniform_independence.log) |
| 2026-09-16T06:58:49.660752+00:00 | 2.477 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_uniform_inventory_gui.py` | [log](reports/b71_apf6/test_apf_uniform_inventory_gui.log) |
| 2026-09-16T06:58:50.036275+00:00 | 13.763 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_wave_integration.py` | [log](reports/b71_apf6/test_apf_wave_integration.log) |
| 2026-09-16T06:58:52.169181+00:00 | 0.154 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_wordmark_regions.py` | [log](reports/b71_apf6/test_apf_wordmark_regions.log) |
| 2026-09-16T06:58:52.354713+00:00 | 66.356 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_workspace_recovery.py` | [log](reports/b71_apf6/test_apf_workspace_recovery.log) |
| 2026-09-16T06:59:03.833395+00:00 | 0.169 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xenia_edge.py` | [log](reports/b71_apf6/test_apf_xenia_edge.log) |
| 2026-09-16T06:59:04.037404+00:00 | 1.769 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xenos_4444_mip_layout.py` | [log](reports/b71_apf6/test_apf_xenos_4444_mip_layout.log) |
| 2026-09-16T06:59:05.840367+00:00 | 0.084 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xenos_4444_png.py` | [log](reports/b71_apf6/test_apf_xenos_4444_png.log) |
| 2026-09-16T06:59:05.955964+00:00 | 0.084 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xenos_extra_formats_png.py` | [log](reports/b71_apf6/test_apf_xenos_extra_formats_png.log) |
| 2026-09-16T06:59:06.070528+00:00 | 1.041 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xex_image.py` | [log](reports/b71_apf6/test_apf_xex_image.log) |
| 2026-09-16T06:59:07.146177+00:00 | 72.482 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xex_image_retail.py` | [log](reports/b71_apf6/test_apf_xex_image_retail.log) |
| 2026-09-16T06:59:23.376203+00:00 | 1.827 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_apf_xma1_wizard_gui.py` | [log](reports/b71_apf6/test_apf_xma1_wizard_gui.log) |
| 2026-09-16T06:59:25.238122+00:00 | 39.435 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_b69_a1_playcalling.py` | [log](reports/b71_apf6/test_b69_a1_playcalling.log) |
| 2026-09-16T06:59:30.065745+00:00 | 9.866 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_provider_integrity.py` | [log](reports/b71_apf6/test_provider_integrity.log) |
| 2026-09-16T06:59:39.964437+00:00 | 0.154 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_product_catalog.py` | [log](reports/b71_apf6/test_product_catalog.log) |
| 2026-09-16T06:59:40.153418+00:00 | 2.067 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_phase1_packaging.py` | [log](reports/b71_apf6/test_phase1_packaging.log) |
| 2026-09-16T06:59:42.254297+00:00 | 0.100 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_capability_registry_module_commands.py` | [log](reports/b71_apf6/test_capability_registry_module_commands.log) |
| 2026-09-16T06:59:42.387371+00:00 | 2.008 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_studio_qt_models.py` | [log](reports/b71_apf6/test_studio_qt_models.log) |
| 2026-09-16T06:59:44.426915+00:00 | 41.388 | 0 | `/home/noah/2k-worktrees/astra-b71-apf6/.scratch/test-python/bin/python3 tests/mod_editor/test_studio_shell_layout_qt.py` | [log](reports/b71_apf6/test_studio_shell_layout_qt.log) |
| 2026-09-16T07:00:23.527465+00:00 | 2.475 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow.py` | [log](reports/b71_apf6/retire-donor-regression.log) |
| 2026-09-16T07:00:26.034104+00:00 | 3.015 | 0 | `python3 tests/mod_editor/test_apf_b71_editor_workflow_qt.py` | [log](reports/b71_apf6/retire-donor-qt.log) |
| 2026-09-16T07:00:29.083323+00:00 | 1.382 | 0 | `python3 tests/mod_editor/test_apf_playcalling_editor_facade.py` | [log](reports/b71_apf6/retire-donor-facade.log) |
| 2026-09-16T07:00:30.497101+00:00 | 9.500 | 0 | `python3 tests/mod_editor/test_provider_integrity.py` | [log](reports/b71_apf6/retire-donor-provider.log) |
| 2026-09-16T07:00:40.029478+00:00 | 21.221 | 0 | `python3 reports/b71_apf6/final_gates.py` | [log](reports/b71_apf6/gates-after-retire-donor.log) |
| 2026-09-16T07:00:40.088542+00:00 | 10.481 | 0 | `python3 packaging/repin.py --apply` | [log](reports/b71_apf6/repin-final.log) |
| 2026-09-16T07:00:50.599179+00:00 | 0.151 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [log](reports/b71_apf6/strict-registry-final-2.log) |
| 2026-09-16T07:00:50.780575+00:00 | 0.060 | 0 | `python3 reports/b71_apf6/audit_delivery.py` | [log](reports/b71_apf6/delivery-audit-2.log) |
| 2026-09-16T07:00:50.872027+00:00 | 0.085 | 0 | `python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt .scratch/apf-release` | [log](reports/b71_apf6/release-stage-final-2.log) |
| 2026-09-16T07:00:50.985463+00:00 | 0.379 | 0 | `env PYTHONDONTWRITEBYTECODE=1 python3 packaging/check_apf2k8_mod_studio_release.py .scratch/apf-release` | [log](reports/b71_apf6/release-check-final-2.log) |
| 2026-09-16T07:00:51.395827+00:00 | 9.845 | 0 | `env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/home/noah/2k-worktrees/astra-b71-apf6/.scratch/apf-release .scratch/test-python/bin/python3 .scratch/apf-release/packaging/check_apf2k8_mod_studio_runtime.py` | [log](reports/b71_apf6/release-runtime-final-2.log) |
| 2026-09-16T07:01:31.474146+00:00 | 0.069 | 0 | `python3 reports/b71_apf6/make_report.py --require-pass` | [log](reports/b71_apf6/aggregate-final.log) |

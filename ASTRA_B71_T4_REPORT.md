# Beta 71 T4: project-open equipment fit recovery

Base: `local/stack-beta-71`, `e2f5c6e6`. Branch: `astra/b71-t4-project-load-equipment-fit`.
Implementation commits: `e67a097f` and `b96f6791`. The final documentation commit carries the evidence and handoff.

## Result

**PROVED offline:** a saved project retains oversized equipment PNGs and every other edit. The affected item displays **needs refit** with the original fit message. Build identifies the unresolved item. Build's **Refit equipment: reduce colours, then size** action checks the selected item, reports measured dimensions, colours and encoded bytes, and creates one Undo entry. A failed refit leaves the edits and Undo history intact.

**UNWITNESSED:** appearance in a running game, Windows/macOS execution, and the unavailable original reported project. No emulator, displayed GUI, audio, network or push was used. Qt ran offscreen. The supplied screenshot path exists, but its image shows an unrelated Discord channel rather than the reported error dialog; it does not independently establish the error or source artwork.

## Root cause, with source locations

Historical line numbers below refer to beta 70 (`3c98d433`, unchanged at this job's base).

1. `mod_editor/core/nfl2k5_uniform_equipment_writer.py:187` constructs **Equipment art cannot fit**. `:620-632` can turn a bounded greedy failure into `budget + 1`, explicitly marked as a lower bound. Thus **at least 6,785** is not necessarily a measured 6,785-byte greedy stream.
2. `mod_editor/core/nfl2k5_uniform_equipment_writer.py:1693` catches that fit error together with other validation failures and raises **Cannot load equipment edits**, appending the advice to remove the edit in the older studio.
3. `mod_editor/studio/session.py:4183` invokes that preflight after unpacking the project and before adopting its edits. The exception prevents the session transaction from committing. `mod_editor/studio/facade.py:3543` creates a disposable candidate and discards it on failure; `:3591` adopts it only after this load succeeds. This is why one failed art item blocks the whole project.
4. Beta 69 already had project-open preflight (`f7d6fc07:mod_editor/core/nfl2k5_uniform_equipment_writer.py:1447`) and the greedy-then-optimal fallback. The load check was **not newly introduced in beta 70**.
5. Beta 70 changed the quantiser and added the stripe floor at `mod_editor/core/nfl2k5_uniform_equipment_writer.py:1080-1083`. Automatically fitting striped art now stops at a palette limit of 16; beta 69 could continue to two. The generated regression below isolates that policy change: disabling only the stripe floor restores the fit; replacing only the quantiser does not. The distance-bit encoder order remains source geometry, then 10/11/12 in both versions.
6. `mod_editor/core/equipment_staging.py:17` pairs normal shoes, gloves and elbow pads with existing mud siblings. It does **not** pair socks. Project restore uses only the PNGs already in the archive and does not invoke that staging fanout. Normal and mud socks occupy two descriptors in the same physical TSET. Naming both in a preflight error does not prove the loader synthesized either variant from the other.

The original project's exact causal combination remains **UNWITNESSED** without its PNGs. The generated project proves an actual beta-69-accepted / beta-70-refused regression and the requested exact greedy boundary, without claiming that it is the original file.

## Reproduction

Run `PYTHONPATH=. python3 tools/b71_t4_equipment_probe.py`.

The probe reads only the selected retail package, constructs deterministic authored three-colour bands with 34 seeded speckles, and loads the original beta 69 and beta 70 writer source from Git. The historical optimal implementation uses the worktree's reviewed executable helper. It never writes decoded retail data or a rebuilt retail span to the repository.

| Measurement | Result |
| --- | --- |
| Retail selector | `22H2`, `tset:3800:4:0:socks00` |
| Physical allocation | outer 3800, chunk 4, offset 139648; body 6,784 bytes; complete span 6,816 bytes |
| Retail system/video/scratch | 256 / 7,552 / 16 bytes |
| Authored RGBA SHA-256 | `177bef6023ec297ef5e8feeeb930c15ab8a5432a8a2497ac0d677b63f038de4a` |
| Beta 69 final candidate, greedy at 10 distance bits | **6,785 bytes**, one over capacity |
| Same candidate through the current optimal fallback | **6,764 bytes**, `optimal_token_parse` |
| Beta 69 emitted body after loader-safe fill | 6,768 bytes, two-colour palette limit |
| Beta 70 normal policy | refuses; smallest result 7,004 bytes with stripe floor |
| Beta 70 with only stripe floor disabled | fits, 6,768 bytes, two-colour limit |
| Beta 70 with only old quantiser restored | still refuses, 7,007 bytes |
| Complete span and wrapper +0x14 | unchanged |

Evidence: [measurements](reports/b71_t4/reproduction/measurements.json), [authored PNG](reports/b71_t4/reproduction/sock.png), [replacement-only project](reports/b71_t4/reproduction/one-byte.2k5mod). The `.2k5mod` was written and reparsed by the production archive functions. Its save-time no-op comparison uses an explicitly synthetic comparison image; the compression measurements use the real pinned retail span in memory.

The exact **6,785 versus 6,784** greedy case and the reported **at least 6,785** diagnostic are distinct assertions. The retail probe proves the former. A separate fault-injection test proves that the latter exact error string survives project open unchanged, alongside a fitting mud edit. It does not pass an injected compressor result off as a measured retail encoding.

## Fix

- `mod_editor/core/nfl2k5_uniform_equipment_writer.py:1661`: preflight catches fit-specific exceptions and returns `fit_status`, exact `fit_error`, byte bounds and retry data. Invalid PNGs, invalid targets, changed source pins and other integrity errors still refuse safely. Fit state is derived again on reopening, so old archives need no schema migration.
- `mod_editor/core/nfl2k5_uniform_equipment_writer.py:1697`: first check the combined physical group. On a miss, check each addition to a fitting subset. A rejected normal variant does not prevent checking mud or later groups. Every accepted subset is recompressed together; independent success is never treated as proof that two edits share the allocation safely. No source edit is dropped or silently resized.
- `mod_editor/core/nfl2k5_uniform_equipment_writer.py:616`: a greedy cutoff now proceeds to bounded optimal encoding before reporting a compressed-size miss. Exact decode, scratch and fixed-span checks remain. The format-only impossibility bound is retained. The helper is mode **0755**, Git mode **100755**, link count 1, passes its pinned size/hash gate, and was actually executed. Existing native/codec tests continue to enforce non-overlapping matches and preserve wrapper +0x14.
- `mod_editor/core/equipment_staging.py:33`: imports and worker-side status checks use the same tolerant measurements. A fitting selected variant can be staged while a different variant remains unresolved. Selected imports that still fail retain their existing explicit retry/refusal contract.
- `mod_editor/core/equipment_staging.py:52` and `tools/nfl2k5_visual_mod_project.py:4071`: Studio and CLI build paths name the unresolved equipment item and its cause. Other project edits remain staged. The output is not published while an included item needs refit; the user can refit or revert that item.
- `mod_editor/core/equipment_staging.py:185`: one-click refit tries colour reductions at the current scale, then smaller scales. It checks the complete prospective project before replacement, including fit status for unresolved siblings, then commits only the selected PNG as one undoable batch. It reports the actual compiled palette count and size, not the requested quantiser limit. Save/reopen and Undo preserve the result and the original artwork respectively.
- `mod_editor/core/equipment_reporting.py:9`, `mod_editor/studio/facade.py:3715`, and `mod_editor/gui/studio_qt.py:8648`: load messages are inline, the Build list shows the exact per-item error, and a selector plus one-click refit button appears for unresolved items. Compression runs in the existing blocking worker; rendering the list uses cached receipts. Controls respect other active Studio operations.

The brief's requirement for an in-studio action authorizes the narrow direct `studio_qt.py` integration. No separate WIRING handoff remains. `packaging/check_2k5_mod_studio_runtime.py` changes are generated digest updates only. No registry text, preset, XBE writer or cave owner changed; registry count delta is zero. The conditional strict registry validator is therefore not applicable. Repin updates are included; integration should perform its usual shared-manifest regeneration without adding a new cave owner.

## Beta 70 T2 claims rechecked

- Its quality analysis correctly describes a new median-cut quantiser and a 16-colour stripe floor. That floor also excludes some previously accepted two-colour saved imports; its report did not test that compatibility boundary. The generated reproduction establishes this omission.
- Its normal/mud discussion refers to shoes, gloves and elbow pads. The current source confirms that scope. It does not establish automatic sock pairing as the cause of this load failure.
- Its atomic combined preflight refused an entire staging transaction. This job retains atomicity for a failing selected import, while allowing a fitting selected variant to coexist with an explicitly unresolved sibling. Project open now has a different contract: retain all valid art regardless of fit.
- Its “fitted at W x H, N colours” receipt and cached caption contracts remain tested. The new “needs refit” branch does not invent dimensions or colours for a failed compile.
- Its warning against silently destructive two-colour stripe imports remains the default. The new colour/size reduction occurs only through the explicit refit action, with an explanation and Undo.
- The prior aggregate equipment-export inventory failures do not recur here. Real inventory-backed tests run in this worktree. The initial composer skip was a missing root XISO alias; a final standalone rerun supplies a temporary read-only symlink and removes it in `finally`.
- Native binding, dirt-selection timing, larger allocation/disc relocation and in-game artwork claims were not expanded. No disc image was built and no game rendering is claimed.

## Validation and command ledger

**Final result: 31 standalone suites passed, 362 test cases, no remaining skips.** The last refit suite ran 12 tests; the final equipment-export rerun ran all 16. Every suite runs as a standalone `python3` process with `QT_QPA_PLATFORM=offscreen PYTHONPATH=.`; the orchestrator runs at most two processes concurrently. Full stdout/stderr is retained.

- [Initial broad run](reports/b71_t4/tests-initial/validation.json): 30 of 31 suites passed. The old J1 wiring suite expected fit failure to abort open, and its lightweight UI stub could not construct the newly added controls. Its corruption test now checks corrupt art; empty refit controls are created only when needed.
- [Broad rerun](reports/b71_t4/tests/validation.json): 31 suites passed. The one initially skipped retail composer test is rerun separately with its source alias present.
- [Final probe, refit, repin and whitespace checks](reports/b71_t4/final-checks.json).
- [Final complete equipment-export suite](reports/b71_t4/final-export.json).
- [Shell command ledger](reports/b71_t4/commands.json): shell batches, observed exit codes, UTC observation times and tool-reported execution time. For asynchronous commands the initial tool time is only time until yielding, not total command duration. Exact standalone-suite durations and start times are in the validation ledgers above; no unmeasured duration is presented as measured.

Earlier development failures remain in their logs: the first refit test attempted to overwrite an archive without `replace=True`; an initial facade stub lacked equipment iteration; the first historical probe referenced the old quantiser through the wrong module. These were corrected and their complete suites rerun. Scratch-only exploratory scripts also had a mock-cache type mistake and a missing mock attribute before the deterministic reproduction was isolated. No failing assertion was relaxed to accept corrupt bytes or an oversized encoding.

### Final command results

All commands below use `QT_QPA_PLATFORM=offscreen PYTHONPATH=.`. UTC starts, durations and complete logs are also retained in the JSON ledgers.

| Command | Start (UTC) | Seconds | Exit |
| --- | --- | ---: | ---: |
| `python3 tests/mod_editor/test_b71_t4_equipment_project.py` | 23:01:47 | 67.812 | 0 |
| `python3 tests/mod_editor/test_b69_j1_fit.py` | 22:59:16 | 12.288 | 0 |
| `python3 tests/mod_editor/test_b69_j1_build.py` | 22:59:29 | 2.436 | 0 |
| `python3 tests/mod_editor/test_b69_j1_wiring.py` | 22:59:31 | 1.424 | 0 |
| `python3 tests/mod_editor/test_b70_t1_build_speed.py` | 22:59:32 | 19.416 | 0 |
| `python3 tests/mod_editor/test_b70_t2_equipment.py` | 22:59:52 | 1.515 | 0 |
| `python3 tests/mod_editor/test_b70_t2_reporting.py` | 22:59:53 | 0.258 | 0 |
| `python3 tests/mod_editor/test_b70_t2_wiring.py` | 22:59:54 | 0.780 | 0 |
| `python3 tests/mod_editor/test_nfl2k5_equipment_import.py` | 22:59:54 | 2.300 | 0 |
| `python3 tests/mod_editor/test_nfl2k5_equipment_consumers.py` | 22:59:57 | 30.083 | 0 |
| `python3 tests/mod_editor/test_nfl2k5_equipment_import_wiring.py` | 23:00:18 | 0.859 | 0 |
| `python3 tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py` | 23:00:19 | 2.005 | 0 |
| `python3 tests/mod_editor/test_nfl2k5_equipment_texture_chain.py` | 23:00:21 | 3.206 | 0 |
| `python3 tests/mod_editor/test_nfl2k5_equipment_texture_native.py` | 23:00:24 | 0.269 | 0 |
| `python3 tests/mod_editor/test_nfl2k5_equipment_retail_roundtrip.py` | 23:00:24 | 15.385 | 0 |
| `python3 tests/mod_editor/test_2k5_uniform_equipment_export.py` | 23:03:00 | 26.616 | 0 |
| `python3 tests/mod_editor/test_project_document_workflow.py` | 23:00:40 | 15.836 | 0 |
| `python3 tests/mod_editor/test_studio_session.py` | 23:00:51 | 0.911 | 0 |
| `python3 tests/mod_editor/test_studio_facade.py` | 23:00:52 | 0.374 | 0 |
| `python3 tests/mod_editor/test_studio_shell_layout_qt.py` | 23:00:52 | 40.654 | 0 |
| `python3 tests/mod_editor/test_studio_qt_models.py` | 23:00:55 | 0.925 | 0 |
| `python3 tests/mod_editor/test_studio_visual_asset_routing.py` | 23:00:56 | 3.527 | 0 |
| `python3 tests/mod_editor/test_facade_external_build.py` | 23:01:00 | 0.326 | 0 |
| `python3 tests/mod_editor/test_uniform_bundle_cross_project.py` | 23:01:00 | 2.790 | 0 |
| `python3 tests/mod_editor/test_nfl2k5_model_project.py` | 23:01:03 | 37.880 | 0 |
| `python3 tests/mod_editor/test_models_project_wiring.py` | 23:01:33 | 9.283 | 0 |
| `python3 tests/mod_editor/test_provider_integrity.py` | 23:01:41 | 9.694 | 0 |
| `python3 tests/mod_editor/test_providers.py` | 23:01:42 | 3.762 | 0 |
| `python3 tests/mod_editor/test_product_catalog.py` | 23:01:46 | 0.167 | 0 |
| `python3 tests/mod_editor/test_phase1_packaging.py` | 23:01:46 | 2.171 | 0 |
| `python3 tools/test_nfl2k5_visual_mod_project.py` | 23:01:48 | 2.512 | 0 |
| `python3 tools/b71_t4_equipment_probe.py` | 23:01:43 | 4.541 | 0 |
| `python3 packaging/repin.py --apply` | 23:02:55 | 11.843 | 0 |
| `git diff --check` | 23:03:07 | 0.652 | 0 |

Commit commands and their timings are in [delivery-code.json](reports/b71_t4/delivery-code.json). The [delivery ledger](reports/b71_t4/delivery.json) records implementation-bundle verification. After the documentation commit the final bundle is regenerated and verified; its receipt accompanies it at `.scratch/bundle-final-verification.json`.

## Delivery and limits

The worktree already had the requested branch at `e2f5c6e6`. The shared Git directory is outside the writable sandbox. Commits therefore live in `.scratch/t4.git`, with the same branch name and base, and are delivered in **`.scratch/astra-b71-t4.bundle`**. The shared worktree index still reports those edits relative to the base; the bundle carries the committed result. All commits use explicit paths. Task input files and the extracted-source symlink are excluded.

The evidence directory contains authored artwork, metadata and logs only. Retail inputs remain read-only. Temporary test spans and comparison PNGs are cleaned by their context managers; no disc or pack copy was made. Scratch remains far below 200 MB.

Still to witness: open the original affected project in the released Studio, inspect its per-item message, use Refit equipment, save/reopen, and inspect socks at close range and distance in game. The generated reproduction and bounded native codec tests do not establish its visual quality or identify the original PNG's precise failure mechanism.

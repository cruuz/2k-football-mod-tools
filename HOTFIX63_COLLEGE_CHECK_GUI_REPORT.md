# GUI_REPORT: "Check my rosters" wired into the ★ Rosters page for beta 63.1

2026-09-09, Claude Fable 5.1, worktree `/home/noah/2k-worktrees/hf63-college-checker`
(branch `local/hf63-college-checker`, based on `hotfix/beta-63.1`, core commit `0ef15ca7`).
No push, no emulator, no GUI display: every Qt run below is `QT_QPA_PLATFORM=offscreen`.

## Delivery

| Commit | Paths |
|---|---|
| `a37cf71b` Rosters: Check my rosters (college scan, repair with undo, export merge) | `mod_editor/gui/roster_editor_panel_qt.py` (+497/-5), `tests/mod_editor/test_nfl2k5_college_check_page_qt.py` (new, 10 tests) |
| `cbb03909` Packaging: ship nfl2k5_college_check with beta 63.1 | `packaging/release-allowlist.txt` (+1), `packaging/check_2k5_mod_studio_runtime.py` (+5), the page test's packaging assertion (+7) |

The three brief files (`GUI_BRIEF.md`, `HOTFIX_CONTEXT.md`, `ASTRA_BRIEF.md`) stay untracked task inputs.
`ASTRA_REPORT.md`, `WIRING.md` and the core module are untouched. `python3 packaging/repin.py --apply`
reported `applied 0 pin update(s)` (no pinned writer changed). No capability registry row was added:
`test_no_capability_is_invisible.py`, `test_validate_all_capabilities.py` and
`test_capability_registry_module_commands.py` do not demand one for a page action and all pass.

The brief asked for one commit per step (scan dialog, repair with undo, disc export merge, saved copy,
packaging). The first four steps all live in the one protected panel file and were built and verified
together, so they are one commit; packaging is the second. Nothing in the saved-copy step needed code:
the existing signed-copy writer (`SaveContainer.write` through `write_copy_to` / `FranchisePanel.write_copy_to`)
writes the repaired composed bytes because the repair is installed into the document; the page test
proves it (`test_repair_installs_with_undo_redo_and_the_signed_copy_reads_back`).

## What the button does

**Where:** ★ Rosters → Checks tab, next to Check this roster / Show my changes / Repair. It is enabled
with nothing loaded.

**With a roster loaded (disc or Xbox save, franchise included):**

1. Composes the current bytes exactly as a save would be written: the franchise page's
   `sync_from_roster()` first (its refusal is shown and stops the check), then `document.to_body()`.
2. Runs `nfl2k5_college_check.scan` on them and opens the **Check my rosters** dialog:
   * one row per finding: Source, Player, Pool, #, Offset, Raw word, Reason (`outside_arena`,
     `off_table`, `invalid_college_name`, `null_reference`), Displays as (the core's static inference,
     never a witnessed claim), Proposed college;
   * **Invalid references** and **Missing references** (null words) are two separate tables; the
     missing table's caption says the game shows a blank college for null and repairing those is optional;
   * **College table issues** lists every unreadable table entry (index, offset, raw word, stored id,
     issue) whether or not a player uses it;
   * **Repair to college**: a combo of every `Scan.colleges` entry (`index: name`, blank shown as
     `(blank)`), preselecting the core's policy (first `None` case-insensitively, else the first blank,
     else entry 0; on a retail table that is ordinal 187 "None"). The Proposed column follows it;
   * **Repair listed college references**, enabled only for a loaded document with findings, a readable
     table and an established layout.
3. Repair: `check.repair(before, source, expected_sha256=scan.sha256, college_index=chosen)` on a fresh
   composition (the core refuses a changed payload); the page's existing ownership boundary on the
   candidate (`validate_save_edit(before, after)` for a franchise, `validate_save(after)` for a roster
   save, the disc path has none beyond the core's strict decode); then install exactly as the page
   installs any composed candidate: `_restore_composed(after, same franchise journal)` + one `UndoEntry`
   for a franchise, `document.adopt_body(after)` otherwise (player object identities and the original
   bytes retained), `check_depth_locks()` with roll-back, then grid, college combo, Checks repair plan,
   selection, dirty state and actions refresh. The receipt (every repaired player with pool/index/offset,
   old word → new word, reason; before/after sha256; "Saved: no" and which button writes it) is shown in
   the dialog and on the Checks tab, and the status line says it is not saved yet.
4. Undo/redo (page buttons, shared with the franchise page) restore the exact prior / candidate bytes;
   redo never re-runs the repair with a different default.
5. Dirty state: an explicit journal keyed `(pool, index)` is unioned into `_dirty` (a repair to a blank
   college has no text diff, since a null and a blank both display `""`), kept by `_after_edit` and by
   `_restore_composed`, and cleared on undo / a new load. `is_dirty()` therefore guards the replace prompt.
6. Export: `edits_document()` merges `names: {"college": <the college text the record holds now>}` for
   every journaled record with its source first/last identity, even when the text is `""`; never
   `fields.college_pointer`. Export roster edits (.json)…, Save disc copy… and the Build & Share
   `roster_edits` step therefore carry the repair. For a disc the receipt replays `rr.apply_body` on the
   original disc body and reports how many of the repaired four-byte words match; with duplicate college
   names the text-only schema lands on the first entry of that name and the receipt says so
   ("entries 3 and 4 are both named 'Marshall'; the text-only export selects entry 3, the first of that
   name").
7. Saved copies: Save Xbox save copy… / Save disc copy… are the unchanged writers (EXTRA recomputed by
   the existing signer, every other member byte for byte, never the source).

**With nothing loaded:** the dialog offers **Choose save…** (`SaveContainer.load` with the unchanged
signature policy, then a read-only scan of `container.savegame`) and **Choose disc…** (pack-0 outer
entry 5 through the existing archive reader `rr._outer_image()` / `rr._entry`, never `load_image`).
When Open Xbox save… verified a container whose roster did not parse (for example a college name
outside the file), the status line says so and Check my rosters… scans that container read-only with
the guidance "did not load on this page, so this check is read-only and Repair is not offered. Load
this file after repair to check it again." The choose buttons are also present with a roster loaded;
a chosen file is only ever scanned, never installed.

## What it refuses (and shows, never bypasses)

| Situation | Behaviour |
|---|---|
| Composed bytes changed since the check (an edit between check and repair) | `RosterRecordError: the roster changed since this check; press Check my rosters… again`; nothing changes |
| Roster reloaded since the check (same bytes or not) | `… the roster was reloaded since this check …`; nothing changes |
| Unreadable college table entry (name outside the arena, unaligned, unterminated, invalid UTF-16) | Repair disabled; the issue and every affected player are listed; a direct call refuses `college table` |
| No college table / overlapping, unbounded, unsupported layout | Repair disabled; the core's diagnostic is kept in the summary and guidance |
| Read-only check (chosen file, or the container that did not load) | Repair disabled; direct call refuses `read-only` |
| Inline MyCareer footer and a different college for MyPlayer | Core refusal `MyPlayer name or college reference changed` shown with the hint to choose the recorded college; the footer is never rewritten; the recorded college repairs cleanly |
| Ownership / depth-lock failure on the candidate | The existing `ValueError` is shown; the candidate is not installed (depth failure rolls back) |
| Unsigned or mismatched save chosen | `SaveContainer.load`'s own refusal (`no EXTRA beside …`), no scan around it |
| Disc whose outer entry 5 is not the main roster | `outer entry 5 is 0x… bytes, not the main roster` |
| Clean roster | Repair disabled: "Every player college word selects a readable college record. Nothing to repair." |

Not implemented (out of scope by the brief): writing a repaired copy of a save that never loaded on the
page (the read-only scan reports it), nearest-address/text guessing, any change to validator strictness.

## Protected files: the smallest change

`mod_editor/gui/roster_editor_panel_qt.py`
* `CollegeCheckDialog(QDialog)` (new class) and, on `RosterEditorPanel`: `_college_composed`,
  `_college_scan`, `college_check_session`, `college_check_path`, `open_college_check`,
  `repair_college_references`, `_college_export_replay`, `college_repair_text` (new methods).
* Existing lines touched: the imports (`struct`, `nfl2k5_college_check`); four state fields in
  `__init__`; the button in `_build_report_page`; `_restore_composed` unions the journal into `_dirty`
  (one expression); `load_document` resets journal/generation/container; `load_save` splits its `try`
  so a verified container whose document fails is retained (status line gains one parenthesis);
  `_after_edit` keeps a journaled key dirty (one `or`); `edits_document` merges the journal; `__all__`.

`packaging/release-allowlist.txt`: `mod_editor/core/nfl2k5_college_check.py` after `nfl2k5_save_rost.py`.
`packaging/check_2k5_mod_studio_runtime.py`: the module in `product_modules` and a `require` that
`scan`, `repair` and `CollegeCheckError` exist.

## Tests: every tail

Standalone, `cd <worktree> && PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/<file>.py`.
All nine suites named in the brief were run before any change (baseline OK) and after.

```
tests/mod_editor/test_nfl2k5_college_check_page_qt.py   (new)
Ran 11 tests in 1.453s
OK

tests/mod_editor/test_nfl2k5_college_check.py
Ran 17 tests in 5.215s
OK

tests/mod_editor/test_nfl2k5_college_check_qt.py
Ran 3 tests in 0.436s
OK

tests/mod_editor/test_roster_editor_panel_qt.py
Ran 50 tests in 9.801s
OK

tests/mod_editor/test_roster_editor_panel_franchise.py
Ran 2 tests in 0.425s
OK

tests/mod_editor/test_nfl2k5_franchise_schedule_college.py
Ran 8 tests in 1.802s
OK

tests/mod_editor/test_studio_shell_layout_qt.py
Ran 18 tests in 84.282s
OK

tests/mod_editor/test_no_capability_is_invisible.py
Ran 14 tests in 0.616s
OK

tests/mod_editor/test_phase1_packaging.py
Ran 17 tests in 1.980s
OK

tests/mod_editor/test_2k5_build_is_explainable.py
Ran 16 tests in 0.017s
OK

tests/mod_editor/test_ux_rosters_words_qt.py
Ran 4 tests in 0.197s
OK

tests/mod_editor/test_nfl2k5_scorebug_template_release.py      (reads the allowlist)
Ran 5 tests in 0.512s
OK

tests/mod_editor/test_shipped_tools_posix_only.py               (reads the allowlist)
Ran 13 tests in 10.687s
OK

tests/mod_editor/test_directory_publishes_are_portable.py       (reads the allowlist)
Ran 5 tests in 0.165s
OK

tests/mod_editor/test_generated_artifacts_are_lf.py             (reads the allowlist)
Ran 4 tests in 4.341s
OK

tests/mod_editor/test_validate_all_capabilities.py
Ran 0 tests in 0.000s
OK (skipped=1)

tests/mod_editor/test_capability_registry_module_commands.py
Ran 3 tests in 0.001s
OK

tests/mod_editor/test_rosters_data_qt.py
Ran 6 tests in 0.558s
OK

tests/mod_editor/test_text_rosters_panel.py
Ran 14 tests in 0.174s
OK

tests/mod_editor/test_roster_save_to_disc_wiring.py
Ran 6 tests in 1.407s
OK
```

Packaging (run in this order, on the working tree that became the two commits):

```
$ python3 packaging/repin.py
would apply 0 pin update(s)
$ python3 packaging/repin.py --apply
applied 0 pin update(s)

$ python3 packaging/stage_release.py packaging/release-allowlist.txt <tmp-stage> .
staged 798 files; 0 declared inputs absent

$ python3 packaging/check_2k5_mod_studio_release.py <tmp-stage>
2K5_MOD_STUDIO_RELEASE_PASS files=798 directories=36 bytes=138043785 metadata=24 private_inventory=false retail=false symlinks=false undeclared=false

$ (cd <tmp-stage> && env -u PYTHONPATH QT_QPA_PLATFORM=offscreen python3 packaging/check_2k5_mod_studio_runtime.py)
2K5_MOD_STUDIO_RUNTIME_CLOSURE_PASS product_modules=228 tool_modules=35 registry=124 sections=12 nfl2k5_capabilities=86 reports=16 reviewed_metadata=24 sets=634 visuals=71963 team_kit_sets=634 team_kit_assets_per_set=39 text_banks=716 text_strings=23346 text_editable=20074 text_read_only=3272 roster_numbers=6522 audio=850 audio_editable=850 audio_export_only=0 audio_streaming_banks=17 audio_streaming_ranges=53571 audio_streaming_wav_ranges=53571 audio_default_scope=playable_54421_standalone_then_ranges audio_replacement_pack_v2=selected_mixed audio_replacement_pack_v3=all_standalone_850 audio_replacement_pack_v4=all_standalone_850_mapped audio_pack_preflight=fully_validated_read_only_preview_then_explicit_apply audio_pack_import=validated_preview_token_apply audio_pack_path_lookup=canonical_850 audio_meaning_confidence=1_152_697 audio_annotations=project_metadata_only_searchable_54421 audio_add_all_matching=bounded_256 audio_detail_layout=scrollable_pinned_actions audio_toolbar_layout=two_row_930 audio_preview_lifecycle=selection_source_epoch_owned_process audio_query_lifecycle=applied_token_debounce_guarded audio_shortlist_clear=one_level_ordered_restore audio_source_failure=transactional_old_catalog_restore audio_waveform=explicit_read_only_session_wav audio_media_invalidation=selection_source_content_owned embedded_audio_task=global_action_guarded_until_drain embedded_operation_task=audio_crib_mutually_exclusive_until_drain audio_bundle_modified_range=user_wav crib=498 crib_editable=498 crib_standalone_editable=182 crib_scene_editable=188 crib_geometry=10_meshes_7_scenes_position_only stadium_scenes=477 stadium_textures_editable=23838 stadium_geometry=same_topology_position_only_private playbooks=37 formations=1533 plays=9251 chains=32502 play_nodes=91833 play_slot_refs=101761 play_assignment_route=same_book_stock_copy_only startup=connected texture_master=direct_source_with_native_edit_layer private_inventory=false retail=false generated_stadium=false
```

The staged panel was byte-compared to the working copy (`cmp` equal) and `git diff --check` was clean
before the commits. The page test's packaging assertion sits in the packaging commit so the wiring
commit is green on its own.

### What the new page test proves (all generated fixtures, real saves never touched)

| Test | Proves |
|---|---|
| `the_checks_tab_offers_the_button_with_nothing_loaded` | button text/placement, enabled with nothing loaded, empty dialog with Repair disabled |
| `rows_list_invalid_and_missing_references_in_both_pools` | a v0 save with an outside primary word, a null primary word and a zero template record: one invalid row (all nine columns checked), two missing rows (primary #1, secondary #0 shown as `#0`), combo of 5 preselecting entry 0, Proposed column follows the combo |
| `repair_installs_with_undo_redo_and_the_signed_copy_reads_back` | signed copy refuses before, repair installs (only 4 bytes differ, object identity kept, college text/index set, journal + dirty), undo restores the exact loaded bytes and clears dirty, redo restores the candidate, signed copy read-back equals the candidate with the receipt's after sha256, `SaveMeta.xbx` copied, source unchanged |
| `a_stale_check_or_a_reloaded_roster_is_refused_and_nothing_changes` | a rating edit between check and repair → refusal, bytes/journal/undo depth unchanged, dialog shows Refused; a fresh check repairs and keeps the rating; a reload invalidates a check |
| `a_broken_college_table_disables_repair_and_a_failed_load_is_still_checked` | unaligned name: document loads, 1 table issue + 3 findings, Repair disabled; name outside the file: page load fails with the guidance, an already-loaded roster stays, a fresh panel scans the verified container read-only (3 findings, 1 issue); no college table: diagnostic kept |
| `repair_to_blank_persists_in_dirty_state_and_the_disc_export` | a disc with a blank entry 1 and an off-table word: policy picks the blank, `document.diff()` is empty yet `_dirty` and `is_dirty()` hold, export carries `names.college == ""` with the source identity, replay on the original body equals `to_body()`, a later rating edit merges into the same entry, JSON export and disc copy carry it (copy has college_index 1 and zero findings), source disc untouched, undo order |
| `duplicate_college_names_export_the_first_matching_entry_and_say_so` | entries 3 and 4 both "Marshall", repair to 4: document holds 4, receipt export entry 3 verified with the note, text says so, the disc copy lands on 3 with the same name |
| `franchise_repair_undoes_and_redoes_around_a_schedule_and_a_rating_edit` | schedule edit + rating edit + repair: franchise journal unchanged, undo restores the exact prior word with both edits intact and the copy refuses again, redo restores the candidate, three undos reach the loaded bytes, three redos return, the signed copy carries the repair, the rating and the franchise edit |
| `an_inline_mycareer_footer_refuses_a_different_college_and_keeps_the_recorded_one` | index 1 refused (shown, nothing installed, no undo entry), index 0 repairs to the original bytes, `career.read` passes, the copy signs |
| `choose_save_and_choose_disc_scan_read_only_and_refuse_an_unsigned_save` | chosen folder and its loose SAVEGAME.DAT give the same read-only session, unsigned save refused by the signature policy, disc scanned through the archive reader (off_table finding), a foreign entry 5 refused, the loaded roster and the chosen source unchanged |
| `the_release_ships_the_core_module` | allowlist and runtime closure name the module |

## Proved offline vs. not

Proved here: the byte contract (only the listed four-byte words change), stale/reload refusals, the
journal in dirty state, the export merge and its replay on the original disc body, undo/redo exactness
around franchise and rating edits, signed-copy read-back, the MyCareer footer refusal, the read-only
paths, packaging closure. All on generated fixtures; the core's own suite additionally scanned the
retail body and the hub's real franchise saves read-only (0 findings) and exercised in-memory faults.

Not proved: anything in-game. The dialog was never displayed (offscreen only), so its proportions at
1366 px are unseen. The tester's actual failing save was never supplied, so its specific cause is still
unassigned (null, outside pointer or a broken table).

## Relay text for BigTimeEmpire (plain, short; add "written by Claude" if posted as-is under Noah's name)

> Beta 63.1 adds a Check my rosters button on the Rosters page, Checks tab. It lists every player whose
> college reference is missing or points outside the college table, on the roster you have loaded, or
> read-only on any save or disc you pick. Repair rewrites only those college words to the college you
> choose (the game's None entry is preselected), with undo, and Save Xbox save copy then writes a
> re-signed copy next to your original. A blank college on its own is not a problem. The refusal you hit
> comes from a college word that points outside the roster arena, and this repair is built for exactly
> that. If the college table itself is unreadable the tool names the affected players but will not guess
> a repair. Please run it on the save that refused and tell us what the player card shows after you load
> the copy. If it still refuses, send the SAVEGAME.DAT and EXTRA and we will look at the actual bytes.

## What Noah must witness

1. **A save with an off-table college.** Open Xbox save… on a save that refused (or make one: the
   tester's, when supplied). Checks tab → Check my rosters…: the rows name the right players; pick None
   (preselected) → Repair listed college references → Save Xbox save copy…. Put the copy on xemu/Xbox,
   load it: the game accepts the save, the repaired player's card shows the COLLEGE line as None (or
   blank if blank was chosen), his ratings and the schedule edits are intact, and a save/load cycle in
   game keeps it.
2. **The disc roster.** Open disc roster… (or Use the open disc) → Check my rosters… → Repair → Export
   roster edits (.json)… → ★ Build & Share with those edits → build; in game, open the repaired player's
   card and check the college line. Also try Save disc copy… directly for the same player.
3. **Read-only Choose save…** on the tester's file with nothing loaded: the counts match what he reported.
4. **Undo in the real window:** repair, undo, redo through the page buttons while the franchise tab is
   showing; the Checks tab receipt and the status line read sensibly at the window's normal width.
5. **A created player with a blank college and a draft prospect** still display as before (the checker
   lists null words as optional "missing" rows; repairing them is a choice, not a fix).

## Notes and judgment calls

* The choose buttons are offered in the dialog whether or not a roster is loaded (the spec asks for them
  without a document); a chosen file is only scanned, never installed, so this adds no write path.
* `load_save` gains one parenthesis on its failure message so the user learns the read-only check exists;
  the existing `string offset` assertion in `test_nfl2k5_college_check_qt.py` still holds.
* Export merge uses the college text the record holds now (not the journal's stored name), so a later
  manual college change on the same player wins, and the journal only says "this record needs an
  explicit entry".
* No file writes were added; the only new file I/O is the read-only archive read for Choose disc….

# r64 Discord Team Kit cross-project import

2026-09-07. Branch `astra/r64-discord-teamkit-import`, base `d9e5cc4`.
**EXPERIMENTAL / UNWITNESSED.** The editor fix and protected GUI handoff are
complete. No game, emulator, display, audio, network request, disc build or push
was used. Qt ran offscreen. Only this worktree and temporary fixtures were
written. No protected file or other worktree was edited.

## Reproduction and decisions

**PROVED:** before changing production code,
`test_fresh_bundle_imports_into_project_with_earlier_torso_edit` exported the
Ravens `02H3` + `02A3` kit from fresh session A, changed its Torso / Jersey PNG,
staged a different torso in session B, and attempted the import. It failed at
`uniform_bundle.py:841` with the exact community error:

> The working pixels changed after export for Torso / Jersey; export a fresh Team Kit bundle before importing

The old guard compared the destination's current PNG digest, decoded RGBA digest
and origin with every export baseline before deciding whether a supplied PNG was
edited. That made untouched exports depend on unrelated destination edits.
The two supplied screenshot descriptions establish the community workflow;
Noah's screenshots themselves and Coach Edwards's project files were not available
as fixtures. No claim is made about having inspected those original files.

The checkout initially lacked ignored `reports/assets` evidence. Metadata for
the existing uniform and texture catalogues was copied from the approved
read-only hub's `builds/2K5-Mod-Studio-v1.0-RC62/reports/assets` into this
worktree's ignored report directory. No source artwork was copied from that
build. The new cross-project suite gives a precise SkipTest when the Team Select
catalogue evidence is absent. Existing suites retain their original evidence
requirements. No evidence or ASTRA_BRIEF is included in the commit/bundle.

## Implementation and report semantics

- A valid supplied PNG whose decoded RGBA digest equals its manifest baseline
  is skipped. Its current destination PNG is not read, restored or staged.
  Re-encoding a PNG without changing pixels is also skipped, even when export
  origin and destination origin differ.
- Every valid PNG that differs from its export baseline is accepted through
  `StudioSession.replace_batch`. Destination divergence is reported instead of
  refused. The transaction still validates all targets/current staged edits
  before mutation and preserves rollback and a single Undo action.
- `TeamKitComponentImport` records physical set, stable asset ID, group, label,
  imported/skipped decision, replaced content (`source` or `your earlier edit`)
  and overwrite classification. Overwrites include replacing a previous project
  edit even when it was the export baseline. This is needed for a sheet exported
  from the main project immediately before it replaces kit-authored digits.
  A destination at source whose pixels differ from a main-project baseline is
  also an overwrite and is labelled `source`.
- `imported_count` counts the bundle's accepted edited components;
  `skipped_unchanged_count` and legacy `unchanged_count` count only untouched
  bundle components. `overwritten_count` is a subset of accepted components.
  Legacy `changed_count` remains the number actually changed by the transaction
  and is the sole trigger for dirty state, recovery and the GUI mutation signal.
  Counts describe the receipt; they are not all measures of new writes.
- An immediate identical repeat validates the complete bundle and staged
  replacements, proves a zero-change batch and adds no Undo action or session
  manifest write. A weak-key, one-receipt-per-session cache preserves its prior
  component attribution/summary/details across service recreation. It is keyed
  by manifest+decoded component content and the session mutation revision.
  Undo/another edit invalidates it. This short-lived receipt is not saved into
  the portable project; a reopened session generates a new current-state receipt.
- Changed incoming bytes are snapshotted into a resolved private temporary
  directory during validation. An external PNG save between the component
  decision and batch staging cannot substitute different bytes. Temporary
  snapshots and extracted ZIPs are cleaned on every ordinary exit/error path.
- Schema, canonical manifest, metadata, source identity, physical-set order,
  asset identity/order, duplicates, missing/undeclared files, PNG size/format,
  dimensions and guide checks remain. Foreign modifications to a staged edit
  still refuse before batch mutation. The new optional `expected_set_selectors`
  service/facade argument rejects a different selected team/style/side set.
  The protected GUI proposal passes the user's selection explicitly.
- No disc, XBE, allocator, archive format, digit splitter/layout or portable
  project format changed. Returning edited pixels to source still uses the
  existing session revert behavior, so shareable projects remain replacement-only.

## Dialog before/after and protected integration

Before, the operation displayed the Torso / Jersey refusal quoted above, with
the existing original-disc safety footer. The old success dialog also inferred
that a zero-change import necessarily matched the export baseline.

After the exact protected patch in
`tests/fixtures/discord_teamkit_import_wiring.patch` is integrated, the two-torso
cross-project example displays:

> Imported: 2. Skipped unchanged: 76. Overwritten: 2. 2 project components changed as one Undo action. Your source XISO was not changed.

Details list all imported and skipped components and the overwrite subset, e.g.:

```text
02H3: Live Uniform / Torso / Jersey (replaced your earlier edit)
02A3: Live Uniform / Torso / Jersey (replaced your earlier edit)
```

The panel retains `Imported: 2. Skipped unchanged: 76. Overwritten: 2.` and the
same component receipt in its tooltip. The ordinary component table continues
showing the project's current Modified/Original state; its total edit count
continues counting the complete project. The shipped panel had no dedicated
last-import receipt row, so the handoff adds one under the private-export warning.
The result dialog uses an expandable Details list to fit a 78-component receipt.
On immediate repeat, the summary and component lists stay identical and the
message says no project pixels changed and no Undo action was added.

The full protected GUI source proposal was executed in memory by all seven
existing Team Kit product integration tests, in addition to three focused
receipt/selection/dirty-state checks. **The actual protected GUI file remains
unchanged**, as required. Its current status text already receives the new
backend message; new dialog lists, persistent panel receipt and selection
forwarding require the exact WIRING handoff. That section also gives the two
updated protected runtime source pins. No new allowlist line, capability,
dispatcher flag, BuildPlan field or preset is needed.

## Cross-project and number-sheet proofs

**PROVED in bounded tests with real PNGs, real session/project transactions,
the existing catalogue and unchanged `nfl2k5_digit_sheet` splitter:**

1. Export 78 components from fresh A. Edit both Ravens style-3 torso PNGs.
   B already has different HOME/AWAY torsos and a horizontal sheet's ten digits.
   Save B as `.2k5mod`, open it in a new session, then import A's kit. Exactly
   two torsos change and both report `your earlier edit`; 76 untouched bundle
   components skip. All ten digit payloads remain byte-exact.
2. Import that same kit using a newly constructed service. Actual changes are
   zero, component receipt/details/summary are identical, mutation revision and
   session manifest bytes are unchanged. One Undo restores both earlier torsos
   together and leaves the sheet's digits intact.
3. Horizontal sheet first, then a fresh-source kit with a changed digit and
   torso: both import; the kit's digit reports `your earlier edit`. Import
   another horizontal sheet through the existing fresh-kit bridge: all ten
   digits update and report `your earlier edit`; the kit torso stays byte-exact.
4. Export from the main project with an edited torso baseline and import a new
   torso: succeeds, reporting the earlier edit. Import the same bundle into a
   source-only session: succeeds and reports the overwritten `source`. Repeat
   preserves attribution; intervening Undo/edit invalidates the old receipt.
5. A differently encoded but pixel-identical export skips without reading any
   destination component. ZIP transport works across projects. Renamed/missing,
   duplicate/reordered/foreign, invalid PNG/dimension and selected-set inputs
   refuse atomically. A corrupted current staged replacement still refuses.
6. Source-return behavior is delegated to the already-tested replacement-only
   session transaction. No original disc is passed to any new writer.

## Performance: 350 replacements

**PROVED hotspot:** an initial cProfile run measured opening 350 replacements at
399.295 instrumented seconds, with 397.920 s in 700 calls to `decode_rgba_png`.
The pure-Python pixel widening/generator path dominated; fsync cost 0.342 s.
This instrumented duration is not UI latency: cProfile heavily magnifies this
function-call-heavy decoder. The same run profiled adding edit 351 (1.169 s)
and the real `_populate_components` table method (0.003 s). Its long repeated
save measurement was interrupted after identifying the decoder; the private
fixture was explicitly removed. No interrupted timing is treated as complete.

The unprotected uniform and extended visual IO now share a cache of successful
strict decodes keyed by **SHA-256 of complete PNG bytes and expected dimensions**.
Every validation still reads the PNG and all existing source/staged digest and
metadata checks still run. New bytes, wrong dimensions and broken CRCs still
reach/refuse in the same strict decoder. A changed file cannot hide behind its
path, size or restored mtime. Retained decoded RGBA is bounded to 64 MiB and
1,024 entries; oversized entries are not cached. Locking protects cache updates,
and no file handles are retained. Unit tests cover reuse, tampering, dimensions,
CRC refusal, eviction and clearing; existing stale-original and privacy suites pass.

A reproducible developer benchmark is committed at
`tests/fixtures/profile_teamkit_import.py`. It builds 350 uniquely coloured,
full-catalogue-dimension replacement PNGs, saves a real `.2k5mod`, clears the
cache for cold open, opens it in another real session, adds edit 351, invokes
the actual offscreen Qt component-table method, and saves twice. Only private
original generation is synthetic; disc extraction and its I/O latency are not
measured. Both modes use identical session/ZIP/PNG operations. `--uncached`
disables only decode reuse to reproduce the original validation path.

Uninstrumented, sequential runs on this Linux host:

| Operation | Original decode path | Bounded decode cache |
| --- | ---: | ---: |
| Open 350 replacements, cold decode cache | 23.400960 s | 23.364032 s |
| Add edit 351 | 0.066009 s | 0.062238 s |
| Refresh 39-component table at 351 edits | 0.002655 s | 0.002560 s |
| Save 351 replacements | 23.134902 s | 0.089388 s |
| Save again | 22.997624 s | 0.089210 s |

The measured save is **258.8 times faster**. The cached run retained 49,102,848
RGBA bytes (46.8 MiB), 702 entries; peak RSS was 254,136 KiB (248.2 MiB), versus
254,304 KiB uncached. Every benchmark fixture was in TemporaryDirectory and
removed before this report. No disc or archive pack was copied or loaded whole.

**HYPOTHESIS:** the protected GUI's per-edit recovery save and its existing
source lock explain why accumulated edits feel slow: saving hundreds of already
validated images repeatedly entered the decoder. The measured unprotected fix
benefits that same save route. Coach Edwards's actual artwork, Windows drive,
PNG mix and autosave interaction were not profiled. Cold open still has full
decode cost; projects whose decoded working set exceeds 64 MiB may evict entries
and see smaller gains. No constant-time save or cold-open improvement is claimed.
No protected GUI performance change is justified by the measured table cost.

Benchmark commands:

```sh
python3 tests/fixtures/profile_teamkit_import.py --uncached
python3 tests/fixtures/profile_teamkit_import.py
```

## Validation

Each suite was launched standalone with `python3 tests/mod_editor/<suite>.py`,
`PYTHONPATH` containing this checkout and its `tools` directory, and
`QT_QPA_PLATFORM=offscreen`. The new tests set their own import paths. A first
plain invocation of the historical Team Kit suite without PYTHONPATH hit its
existing import-bootstrap limitation; rerun with the CI-style path passed.
The initial one-test regression failed with the exact torso error before the
fix. One intermediate new-sheet assertion compared PNG encoding bytes rather
than pixels; it was corrected to compare RGBA. The final cross-project suite
passes all eight tests.

| Standalone suite / run | Result | Test seconds |
| --- | --- | ---: |
| `test_2k5_stale_original_cache` | 9 passed | 0.014 |
| `test_2k5_visual_io_routing` | 4 passed | 0.110 |
| `test_all_texture_lane-retail` | 13 passed | 16.683 |
| `test_all_texture_lane` | 15 passed, 13 skipped | 0.032 |
| `test_all_textures_workspace-retail` | 3 passed | 4.630 |
| `test_all_textures_workspace` | 18 passed, 3 skipped, 2 evidence errors | 3.801 |
| `test_discord_bugs_2` | 11 passed | 1.047 |
| `test_discord_bugs_2_research` | 4 passed | 0.209 |
| `test_discord_bugs_2_wiring` | 4 passed, 2 skipped | 0.760 |
| `test_linear_texture_dimensions` | 7 passed | 0.000 |
| `test_nfl2k5_digit_sheet` | 3 passed | 0.044 |
| `test_nfl2k5_extended_visuals` | 9 passed | 0.333 |
| `test_nfl2k5_source_cache_privacy` | 7 passed | 0.005 |
| `test_nfl2k5_uniform_catalog` | 5 passed | 0.995 |
| `test_png_import_accepts_real_pngs` | 11 passed | 0.056 |
| `test_studio_facade` | 11 passed | 0.012 |
| `test_studio_session` | 18 passed | 0.511 |
| `test_team_kit_bundle` | 7 passed | 22.946 |
| `test_team_kit_product_integration` | 7 passed | 30.378 |
| `test_teamkit_import_wiring` | 3 passed | 0.351 |
| `test_texture_editor` | 21 passed | 0.905 |
| `test_texture_master` | 11 passed | 0.027 |
| `test_texture_master_facades` | 2 passed | 0.001 |
| `test_uniform_bundle_cross_project` | 8 passed | 69.370 |
| `test_uniform_sharing` | 4 passed, 4 evidence errors | 0.013 |
| `test_visual_decode_cache` | 3 passed | 0.003 |
| `test_team_kit_product_integration (proposal)` | 7 passed | 30.757 |

The table records **249 test executions: 225 passed, 18 skipped and six
missing-evidence errors**. Sixteen of the initial skips were then run successfully
as the separately listed retail-target/cross-pack cases using a temporary local
symlink to the approved extracted tree. It was removed immediately afterward.
Those reads use bounded existing archive descriptors and fixed target spans;
no real-disc build was needed. The two remaining skips are bugs-2's deliberately
deferred APF GUI `_stage_session` integration.

The six errors are baseline evidence gaps, not hidden or converted into success:

- `test_all_textures_workspace`: 18 passed, three initially skipped, two errors
  from registry file-check mode requiring absent `docs/research/apf_audio.md`.
  Its three retail cases subsequently passed.
- `test_uniform_sharing`: four passed, four errors because the ignored APF
  pants, helmet and shoulder layout JSON reports are absent. They were also
  absent from the approved hub search. The NFL sharing metadata is available.

Both whole suites were rerun after executing the four changed production
modules' **original HEAD source in memory**. They produced the identical two
registry/four APF evidence errors (3.985 s and 0.011 s). No registry, protected
checker or evidence was altered to silence them.

`git apply --check tests/fixtures/discord_teamkit_import_wiring.patch`,
`git diff --check`, compilation of changed modules, and three focused proposal
checks pass. The complete seven-test protected GUI proposal run also passes;
no GUI source file was patched on disk. The existing 11-test standard PNG suite,
nine-test stale-original suite and seven-test cache-privacy suite pass.
No unrelated XBE gate was required because no executable owner changed.

## Noah's witness list and known gaps

1. After integrating WIRING, use the original game source and actual Coach
   Edwards-style Ravens HOME/AWAY style-3 working kit. In a main project with
   existing jerseys and number sheets, import edited torso PNGs and inspect
   the imported/skipped/overwrite details, including side and family names.
2. Confirm untouched number PNGs preserve the main project's sheet edits.
   Change one digit in the kit and verify `your earlier edit`; import a
   horizontal sheet afterward and verify the same attribution for the kit digit.
3. Repeat a kit import immediately: identical component receipt, no new dirty
   revision or Undo entry. Undo once should restore the prior imported group.
4. Export directly from the main project, edit its files and import again.
   Select a wrong team/style or side scope and confirm an atomic refusal.
5. Save/reopen the replacement-only project; confirm both teams and all number
   changes remain. Verify the original disc's streaming SHA-256 stays unchanged.
6. Time open, one edit, component refresh and save with 350 actual replacements
   on Windows and the user's working drive. Compare repeated saves; note large
   texture dimensions that exceed the bounded cache's working set.
7. For game appearance, build through the already supported workflow later and
   inspect live torso/helmet families, jersey/arm/helmet digits, HOME/AWAY and
   Team Select cards. No gameplay, palette fitting or visual seam witness is
   claimed by these editor tests.

The FAQ now includes the current-beta workaround: export FROM THE MAIN PROJECT,
copy only edited PNGs with matching names into that new bundle, keep its manifest
and guide, and import. Working bundles remain private; share `.2k5mod` only.

## Delivery

The explicit-path `git add` attempt failed because the worktree's Git metadata
is read-only (`index.lock: Read-only file system`). The authorized fallback is
`.scratch/r64-discord-teamkit-import.bundle`, with a commit on the same branch
name made using isolated scratch Git metadata and the unchanged original HEAD
as its parent. The original worktree index/branch remain unchanged. The bundle
is verified against that parent; its commit contains only the 14 listed task
files. ASTRA_BRIEF.md, .scratch, copied ignored evidence and protected files are
excluded. No push was attempted.

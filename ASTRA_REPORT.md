# Beta 67 P4: CPU Play Calling editor

Branch `astra/b67-p4-studio`, based on `653cb708`. The branch already had the
requested name and base when work began. P3's new core API modules are absent
on this base. No core writer, protected `gui.py`, canonical registry,
allowlist, packaging gate, or unrelated worktree was edited.

## Delivered

- `playcalling_editor_qt.py`: team-first CPU Play Calling tab, 24-team picker,
  offense/defense selection, current shared-book notice, stock/USER/global
  donors, single/all-team ownership plans reviewed before staging, 13 offense
  situations including custom inputs, and 11 defensive personnel rows.
- Worker predictions call P3's exact `Situation`, `predict_offense` and
  `predict_defense` names. The 32-entry cache keys book SHA, MASTER SHA,
  tendency, side and situation values. Generation, source and session checks
  reject stale callbacks and reviews. The grid prints requested row,
  categories, formations, plays, percentages and the model's notes.
- Three formation rating sliders; play X rating; primary/secondary personnel;
  formation removal and category retirement with row coverage and named
  retirements; team run/pass tendency; automatic CPU audible balancing.
  Current individual audible slots remain in Fine-tune Plays. Each new
  control and retained experimental control has a plain one-sentence tooltip
  and accessible description; key behavior is also printed beside controls.
- MASTER personnel is a collapsed, unchecked EXPERIMENTAL group, explicitly
  marked as changing every book. It lists 28 categories and eleven roles,
  edits rows/roles through P3's writer, and stages the 5-2 row-13 fix.
- Experimental offense/defense curve presets prepare canonical TOML and use
  P2's installer, consent/config readback/rollback, status and removal. They
  use a separate managed file from the retained P2 pass-fetch experiment.
  One curve preset replaces the previous curve preset, stated on screen.
- One authored session recipe contains ordered edit receipts. Every staged
  action records Undo; Save Project/load preserves the recipe and its hash.
  Existing SPLB selectors and Scheme Presets precede it. Build rejects a
  changed reviewed value instead of silently overriding another edit.
- The copied-game build finalizer inserts all requested clones in one core
  batch, resolves remaining edits by filename hash, reparses written content,
  compares bytes outside the content allocations and writes
  `book-content-receipt.json`. Receipt rows include before/after values,
  removed formation names, retired category names, MASTER edits, tendency and
  clones. Existing receipt indices are remapped after insertion. The returned
  build receipt names the teams now owning books.
- `WIRING.md` starts with complete GUI import/route/completion-message blocks,
  proposed registry rows and bindings, allowlist lines, runtime imports and
  explicit P3 acceptance details. The page guide and alpha.88 changelog
  bullets quote Urianus and distinguish proof from unwitnessed integration.

## PROVED

The proof here is bounded product behavior using synthetic inputs, not the
new P3 selector or writer math. All fake contract implementations are confined
to `tests/mod_editor/test_apf_playcalling_editor_*.py` and injected through the
facade. No production function substitutes invented distributions or bytes.

Standalone commands run:

```sh
QT_QPA_PLATFORM=offscreen python3 -m tests.mod_editor.test_apf_playcalling_editor_facade
QT_QPA_PLATFORM=offscreen python3 -m tests.mod_editor.test_apf_playcalling_editor_qt
python3 -m tests.mod_editor.test_apf_playcalling_editor_build
python3 -m tests.mod_editor.test_apf_playcalling_editor_patches
QT_QPA_PLATFORM=offscreen python3 tools/apf_gui_replay_offscreen.py --playcalling-contract-only --receipt /tmp/b67-p4-replay.json
python3 -m mod_editor.apf_studio.playcalling_service --help
python3 -m mod_editor.apf_studio.playcalling_patches --help
```

Latest completed outputs at the implementation checkpoint:

- Facade: `Ran 7 tests ... OK`. Includes recipe/Undo/project round-trip,
  all controls, donor isolation, warning/refusal, stale reviews, cache,
  malformed payloads, proposed registry schema and new-file closure.
- Qt: `Ran 8 tests ... OK`. Real widgets with the facade injection, both
  grids, every lever, MASTER, plan table, explanations, consent cancellation,
  stale workers and the worker replay.
- Build: `Ran 2 tests ... OK` (43.684 seconds with other tests running).
  Uses the real existing clone compiler, H7A transport and verifier on a
  synthetic two-pack archive. Inserts 24 clones once, then reparses the
  specifically named clone's changed ratings and unchanged shared donor.
  A changed reviewed input refuses before archive writes.
- Patches: `Ran 2 tests ... OK`. Both presets/profiles with fake canonical
  curve documents, actual P2 installer/config behavior, no-consent refusal,
  tampered-payload refusal, changed-target refusal, status and removal.
- Replay: six steps passed in 11 QThread workers, with 24 teams and 13 rows:
  load context/grid; stage ratings/recompute; review own-book table; stage
  own book; save/reopen/replay; Undo/recompute. Receipt explicitly says
  synthetic contract replay and UNWITNESSED P3/gameplay integration.
- Python compilation and `git diff --check` pass.

The broad regression run executes every discovered `test_apf_*.py` in its own
Python process, offscreen, with `PYTHONPATH` set to this worktree. Full outputs
are private scratch logs at `/tmp/b67-p4-test-logs`; final counts and reruns
are recorded below after the run completes. No game/emulator was launched.

## UNWITNESSED and integration prerequisites

- The main window still imports the legacy class until the protected import
  block in `WIRING.md` is applied. Registered, rendered and usable are separate
  facts; this branch proves the new standalone tab and supplies the wiring.
- P3's real model/writers, real curve payloads, and their combined Studio build
  are UNWITNESSED on this branch. The proposed registry rows become
  `offline-writer-proved` only after P3 acceptance; runtime remains
  `not-tested`. No production stubs were added to make this base seem complete.
- `LINEUP_CALLERS = "unclassified"` keeps the old refusal for uncovered rows.
  Set it to `"non_cpu"` only if P3 proves that classification, or `"cpu"` if
  P3 proves CPU reachability. All paths show coverage. Tests prove the warning
  behavior without claiming the classification itself.
- The required higher-rating sentence is visible. The detailed 0–20 / 2–7 /
  2–5 yard interpolation wording comes from merged P1. Reconcile it with
  P3's exact final report wording before release.
- P3 must accept the documented curve tuple lengths and retain the P2-style
  `PatchDocument.as_toml()` serializer. The contract did not define serializer
  details or curve tuple length; the exact authored presets are in WIRING.
- P3 must support the combined clone batch if both sides are authored in one
  session. P2's existing `_requests` rejects duplicate team indices even for
  different sides. P4 does not bypass that guard or modify its core owner.
- Previews compose existing Fine-tune SPLB edits and Scheme Presets. Other
  editors that change a reviewed field are detected by before-value checks at
  build. An unrelated MASTER/ROST change is preserved by the finalizer's
  load-from-finished-output order. The real combined-source path still needs
  P3/integrated tests.
- Full game-copy builds were not run. `/` had 85 GB free, below the 100 GB
  floor. All archive tests use tiny synthetic packs. No retail bytes, images,
  saves, decoded books or executable files were copied into the repository.
- The full canonical registry file-check gate is blocked on the base by
  missing `docs/research/apf_audio.md` (`validate_registry.py:129`). The new
  fragment passes schema validation merged in memory, and its own evidence,
  command module and validation paths exist. The canonical registry is intact.
- Installer-suite staging is blocked by a different missing base file:
  `tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md`, requested at
  `tests/mod_editor/test_apf_studio_installer.py:41`. Neither missing path is
  present in `git ls-tree 653cb708`. No protected test or gate was weakened.

Noah must witness actual calls for edited team-owned books on BASE/TU 1.1:
heavy sets at goal line, tight ends on third downs, removed stock formations
remaining absent, 5-2 in ordinary defense after the experimental MASTER edit,
team tendency differences, retained audibles, and both Xenia experiments with
status matching the selected launch config. Record those separately from the
bounded offline tests.

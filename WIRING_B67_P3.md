# Beta 67 P3 wiring, as applied to the stack (2026-09-12)

Integration record for `astra/b67-p3-game` (bundle commits `045667e9`, `691add51`, `4c47bef8`).
P3's own request text follows verbatim below; this header records what landed and what did not.

APPLIED
- `mod_editor/capabilities/registry.v1.json`: all eleven `apf2k8.playbooks.*` rows inserted and the
  array re-sorted by id, written as `json.dumps(obj, indent=2, sort_keys=True) + "\n"`.
  Three corrections were required because the rows as supplied are rejected by
  `mod_editor/capabilities/validate_registry.py` (they validate against the JSON schema only):
  * `backend.command` was `null` on every row; the validator requires an active operation to carry a
    command that resolves to the exact backend module. Each row now carries the house
    `"Python API: mod_editor/core/<module>.py <call>"` form used by the other library-only rows.
  * `gui.mode` was `deferred` on every row, which the validator only accepts for the `unknown` and
    `unsafe/deferred` classifications. The eight `offline-writer-proved` rows are now `edit`, the two
    `read-only-mapped` rows (`row_coverage`, `selector_preview`) are `view`, and every row keeps
    `expose: false`, `default_enabled: false` and P3's deferral reason, so nothing is rendered.
  * `apf2k8.playbooks.category_curves` carried `operation: export` with `offline-writer-proved`;
    it is now `write`, matching the sibling `apf2k8.playbooks.pass_fetch_te_bias` patch-export row.
- `packaging/apf2k8-release-allowlist.txt`: `docs/mod_editor/apf_b67_play_calling.md` and the four new
  `mod_editor/core/apf2k8_{master_writer,playcall_curves_patch,playcall_model,team_tendency}.py`.
  The 2K5 allowlist is unchanged, as P3 requested.

NOT APPLIED, with the reason
- The seven `tests/mod_editor/test_apf_b67_*.py` entries and `docs/research/apf_b67_static_audit.json`:
  neither allowlist ships any `tests/` or `docs/research/` file (0 such entries in either list), so
  adding them would change what the product stages, not just what is proved.
- `tools/apf_b67_static_audit.py`: it imports `capstone` and needs pinned retail images. No shipped
  tool in either allowlist imports capstone, and `tests/mod_editor/test_shipped_tools_are_self_sufficient.py`
  holds shipped tools to a plain-import rule. It stays a repository research tool.
- The `facade.py` `install_xenia_patch` replacement body: P4 delivered its own curve installer
  (`mod_editor/apf_studio/playcalling_patches.py`) with P2's consent dialog, a managed filename, and
  status/removal controls, which is what P3 asked for functionally. The facade keeps the pass-fetch
  path and the tab routes curve installs through `playcalling_patches`.
- The `build.py` / `project.py` / `session.py` `asset_name_bindings` persistence blocks: these are the
  P4-owned project-manifest work P3 itself marks unproved ("A real saved crest + field-art + 48-clone
  project has not been built and reopened"). P4's `playcalling_build.finalize` performs the single
  `compile_unlock` + `build_new_folder` clone transaction; manifest rebinding stays open, and open
  item 4 is not described as closed.
- No `packaging/check_apf2k8_mod_studio_runtime.py` change was requested by P3; the new core modules
  enter that import closure through P4's wiring instead.

----- P3's WIRING.md text, verbatim -----

These instructions append to the prior jobs' wiring. P3 did not edit P4's
Studio files, either release allowlist, or the protected capability registry.
All new features remain unrendered until P4 integrates and verifies them.

## Decisions P4 must preserve

- Raw formation 7/7/7 is weak, not strong. Native category weight is 0.1;
  raw 0/0/0 gives 3.0. If a visual strength scale is reversed, explicitly
  convert it before calling the unchanged raw API. Do not silently promise
  the requested raw-7 heavy/raw-0 Ace goal-line recipe will select heavy.
- MASTER roles and rows affect every book, including all team clones.
- Per-team row arrays ARE read at 84929B4C..84929E44, but feed an optional
  cache that the ordinary CPU category lottery does not consume. Hide this
  as a normal play-calling lever or label it as an expert cache edit.
- Do not downgrade the 66.1 retirement guard on a claim of CPU exclusion.
  The two resolver callsites supply both team managers; their parent entry
  lifecycle remains unclassified. Static evidence is in
  docs/research/apf_b67_static_audit.json.
- Defensive play estimates assume lineup feature 4, which is HYPOTHESIS.
  Preserve CallDistribution.notes visibly; do not advertise exact live odds.
- Special formation IDs 151..162 are refused by removal pending separate
  special-tail/cache repair. Ordinary removal is natively stable.

## Patch installer wiring

File: mod_editor/apf_studio/facade.py. Replace the body of
ApfStudioFacade.install_xenia_patch (the existing method at line 2265; use
the actual containing class name) with the following. The curve installer
reuses P2's atomic/config primitives and a separate filename, preserving the
pass-fetch patch. Existing consent remains required.

```python
from mod_editor.core import apf2k8_playcall_curves_patch as curves
from mod_editor.core.apf2k8_playcall_model import PlaycallError

try:
    curves.canonical_curve_payload(Path(path).read_bytes())
except PlaycallError:
    return self.launcher.install_pass_fetch_patch(path, consent=consent)
return curves.install_xenia_patch(
    path, self.launcher.settings.patches_folder,
    self.launcher.settings.emulator_config, consent=consent,
)
```

The curve installer is covered with a fake Xenia directory by
`python3 -m tests.mod_editor.test_apf_b67_writers`. The actual facade is not
changed or claimed verified by P3. P4 must add curve-aware status/removal
controls rather than using pass_fetch_status to report the curve file.

## One-pass archive build and project binding

Core entry point: apf2k8_book_clone.compile_unlock(index, requests,
asset_replacements=by_name). The new optional argument maps **filename hashes**
to complete IFF allocations already compiled by the art/roster/book writers.
ROST overlays are bound after their edits; donor overlays are copied after
their edits. A scheme preset is applied to the authored donor and shared
MASTER overlay, preserving the donor ratings; it does not reread an unedited
source body. The directory is inserted once and the last pack is appended
once. verify_unlock compares every unrelated original pack byte.

File: mod_editor/apf_studio/build.py, ApfBuildService.build, after all
writer groups have produced `compiled`, before its output-copy stage. P4's
project clone requests must enter this transaction, not a second folder
build. The concrete core call is:

```python
from mod_editor.core import apf2k8_book_clone as clone

archive = apf_outer.parse_archive(self.source.index_0a)
by_name = {archive.entries[outer].name_id: payload
           for outer, (payload, _receipt) in compiled.items()}
plan = clone.compile_unlock(
    self.source.index_0a, clone_requests, asset_replacements=by_name,
)
receipt = clone.build_new_folder(
    plan, output_game, lambda message: progress(message, 0, 1),
)
```

P4 must adapt the final dictionary into its BuildReceipt and existing atomic
staging/replace workflow. Do not replace an existing folder directly with
this call; the core deliberately accepts a new destination only.

Save a filename map for every source outer used by the project, not only
books. The map contains identifiers, no retail payloads:

```python
bindings = clone.asset_name_bindings(index_0a, referenced_outer_indices)
# Persist as JSON string keys / integer values in project.json.
manifest["asset_name_bindings"] = {str(k): v for k, v in bindings.items()}
# On reopen against the built folder:
remap = clone.resolve_asset_bindings(
    built_index, {int(k): v for k, v in manifest["asset_name_bindings"].items()},
)
```

File: mod_editor/apf_studio/project.py: add optional asset_name_bindings to
save_project and allowed_manifest_fields; validate keys as distinct
nonnegative decimal indices and values as uint32 before resolution. File:
mod_editor/apf_studio/session.py: each writer-family's asset-id/metadata
rebinder must use this remap before validation, including crest/logocache,
field-art, textures, localization, ROST and MASTER/SPLB providers. This
family-specific project rebinding is **not implemented or proved by P3**.
Do not describe open item 4 as fully closed until an actual saved art project
reopens against its built folder. The P3 test proves the transport and
filename-binding primitives on every asset of a synthetic archive.

The 24+24 planner uses existing ROST strings: offensive resources take the
team name, defensive resources take distinct label names. No string capacity
is guessed, and all existing strings are byte-preserved. Compile both sides
together via `tuple(a.request() for a in offense_plan + defense_plan)`.

## APF release allowlist additions

File: packaging/apf2k8-release-allowlist.txt. Add these explicit entries,
then sort with the existing house convention. The 2K5 allowlist
packaging/release-allowlist.txt needs **no change**.

```text
docs/mod_editor/apf_b67_play_calling.md
docs/research/apf_b67_static_audit.json
mod_editor/core/apf2k8_master_writer.py
mod_editor/core/apf2k8_playcall_curves_patch.py
mod_editor/core/apf2k8_playcall_model.py
mod_editor/core/apf2k8_team_tendency.py
tests/mod_editor/test_apf_b67_clone.py
tests/mod_editor/test_apf_b67_defense_model_native.py
tests/mod_editor/test_apf_b67_model_native.py
tests/mod_editor/test_apf_b67_model_edges_native.py
tests/mod_editor/test_apf_b67_static_audit.py
tests/mod_editor/test_apf_b67_writers.py
tests/mod_editor/test_apf_b67_writers_native.py
tools/apf_b67_static_audit.py
```

Do not ship the root handoff files, delivery bundle, extracted symlink or
retail inputs. The extended SPLB and clone modules are already allowlisted.

## Capability registry rows

File: mod_editor/capabilities/registry.v1.json, insert the following rows
into capabilities and sort by id. All eleven rows validate against the current
registry.schema.json. GUI exposure remains deferred until P4's actual
integration tests pass. validation_command uses standalone unittest modules.

```json
[
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_playcall_curves_patch.py",
      "operation": "export"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.category_curves",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Opt-in pinned BASE/TU curve export; install separately from pass-fetch. Affects every team on that executable."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Opt-in pinned BASE/TU curve export; install separately from pass-fetch. Affects every team on that executable.",
    "surface": "scripts_config",
    "title": "Experimental category distance curves",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers_native"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_splb_writer.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.formation_categories",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Edit primary and secondary membership and retire a category from all surviving records."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Edit primary and secondary membership and retire a category from all surviving records.",
    "surface": "scripts_config",
    "title": "Formation categories and retirement",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_splb_writer.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.formation_ratings",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Write the three raw trailer ratings. Lower numbers increase category weight; 7 is not strongest."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Write the three raw trailer ratings. Lower numbers increase category weight; 7 is not strongest.",
    "surface": "scripts_config",
    "title": "Raw formation ratings",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers_native"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_master_writer.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.master_personnel",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Edit the shared category role bytes or personnel row. Every book on the disc is affected."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Edit the shared category role bytes or personnel row. Every book on the disc is affected.",
    "surface": "scripts_config",
    "title": "Shared MASTER personnel roles and rows",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers_native"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_book_clone.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_clone.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.own_books",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Compile 48 distinct clones plus filename-addressed asset allocations in one archive transaction. Synthetic archive proof only."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Compile 48 distinct clones plus filename-addressed asset allocations in one archive transaction. Synthetic archive proof only.",
    "surface": "scripts_config",
    "title": "Own offensive and defensive books for 24 teams",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_clone"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_splb_writer.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.play_ratings",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Write X bits without changing Y audible tags; 0 has greatest initial weight."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Write X bits without changing Y audible tags; 0 has greatest initial weight.",
    "surface": "scripts_config",
    "title": "X play ratings",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_splb_writer.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.remove_formation",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Remove every duplicate ordinary record, compact and reach the native stable normal form. Special removal is refused."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Remove every duplicate ordinary record, compact and reach the native stable normal form. Special removal is refused.",
    "surface": "scripts_config",
    "title": "Remove an ordinary formation",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers_native"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_splb_writer.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.retire_category",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Remove primary and secondary references, promoting a surviving secondary; refuse to leave a formation with no category."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Remove primary and secondary references, promoting a surviving secondary; refuse to leave a formation with no category.",
    "surface": "scripts_config",
    "title": "Retire a personnel category",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_splb_writer.py",
      "operation": "inspect"
    },
    "classification": "read-only-mapped",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.row_coverage",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Report categories reachable by the separate lineup ladder. CPU-only safety has not been proved."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Report categories reachable by the separate lineup ladder. CPU-only safety has not been proved.",
    "surface": "scripts_config",
    "title": "Lineup row coverage",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers_native"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_playcall_model.py",
      "operation": "inspect"
    },
    "classification": "read-only-mapped",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_model_native.py",
      "tests/mod_editor/test_apf_b67_model_edges_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.selector_preview",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Cold scrimmage preview; empty history and neutral skill. Defensive lineup feature 4 is a hypothesis."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Cold scrimmage preview; empty history and neutral skill. Defensive lineup feature 4 is a hypothesis.",
    "surface": "scripts_config",
    "title": "Offline call preview",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_model_native"
  },
  {
    "backend": {
      "command": null,
      "module": "mod_editor/core/apf2k8_team_tendency.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/mod_editor/apf_b67_play_calling.md",
      "tests/mod_editor/test_apf_b67_writers_native.py"
    ],
    "game": "apf2k8_xbox360",
    "gui": {
      "default_enabled": false,
      "expose": false,
      "mode": "deferred",
      "reason": "P3 core implementation; P4 integration is pending. Registered does not mean rendered or usable."
    },
    "id": "apf2k8.playbooks.team_tendency",
    "input_constraints": [
      "Owned decoded SPLB/MASTER/ROST or a separate owned game folder. Never modify retail in place.",
      "Follow the team tendency pointer; write +5A and the optional row arrays, whose cache is separate from the ordinary CPU lottery."
    ],
    "portme": [
      "Complete P4 wiring and collect the documented gameplay witness."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [],
      "scope": "Bounded native or synthetic proof only. On-field gameplay is UNWITNESSED.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [],
      "notes": "Use the signatures in BETA67_API_CONTRACT.md; notes travel with every preview."
    },
    "source_container": {
      "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
      "hash_pins": [
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
      ],
      "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
      "retail_file": "user-owned extracted APF Xbox 360 game folder"
    },
    "summary": "Follow the team tendency pointer; write +5A and the optional row arrays, whose cache is separate from the ordinary CPU lottery.",
    "surface": "scripts_config",
    "title": "Team run tendency and optional row cache",
    "validation_command": "python3 -m tests.mod_editor.test_apf_b67_writers_native"
  }
]
```

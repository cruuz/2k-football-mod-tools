# The game-module contract — `vc_game_module/v1`

> Normative. Contract version **1.0 (unreleased)**; the number is `CONTRACT_VERSION` in
> `mod_editor/games/contract.py`, the history is `mod_editor/games/CONTRACT_CHANGELOG.md`, and
> the files that *are* the contract are pinned in `mod_editor/games/CONTRACT_PINS.json`
> (section 12). The design rationale and the migration of the existing products are in
> `MULTI_GAME_INTERFACES_PLAN.md`; the how-to is `ADDING_A_GAME_MODULE.md`.

## 1. Scope

A **game module** is a directory `mod_editor/games/<game_id>/` that the core hosts without
knowing the game. The core discovers it, merges its fragments, proves it with a generic
conformance harness on the module's own synthetic source, and lists it in the studio's
**File ▸ Select other games…** chooser. A module reaches the core only through this contract.

Four rules govern everything below:

1. **Passive.** A game never edits an upstream file; the core never imports a game by name.
2. **Fail closed.** A wrong contract version, a malformed identity or a lane that does not
   answer the protocol is refused *with a sentence*, never half-loaded.
3. **Retail-free.** Catalogues carry names, offsets, lengths and digests; never payload.
4. **Fixed allocation, independently verified.** A build reads the source read-only, writes a
   destination that must not exist, declares every byte range (or file) it changes, and ships
   a verifier that re-derives the claim and can fail.

## 2. Terms

| term | meaning |
|---|---|
| core | `mod_editor/games/` minus the game directories: contract, discovery, merge, harness, chooser, pins, tooling |
| game module | one directory under `mod_editor/games/`, its `game.json`, fragments and `GAME` |
| lane | one editable surface of one game = exactly one capability-registry row |
| fragment | a per-game mirror of a canonical file: registry rows, allowlist lines, pins |
| format package | a shared container/format implementation under `mod_editor/games/_formats/` |
| hook | one of the two upstream lines that reach the games package (section 13) |

## 3. A game module

```
mod_editor/games/<game_id>/
  __init__.py               exposes GAME (a GameModule)
  __main__.py               `python -m mod_editor.games.<game_id>` → show / open a window
  game.json                 the manifest (section 5.1)
  registry.fragment.json    the game's games[] entry, declared surfaces, rows (5.2)
  allowlist.fragment.txt    the files the game ships (5.3)
  pins.json                 the counts the game's own tests assert (5.4)
  …lanes, validators, data
tests/mod_editor/test_<game_id>_*.py
```

`GAME = GameModule(contract, identity, identifier, lanes, windows, manifest, package)`.
Construction validates the contract version, unique lane ids and capability ids, unique
window ids and flags, that every lane answers the protocol, and that the manifest agrees with
the identity and the directory. `GameModule.version` is the manifest's `version`.

## 4. The frozen public surface

Everything importable from `mod_editor.games.contract`, name by name. The table is what
`tests/mod_editor/test_games_contract.py::EXPECTED_SURFACE` pins; adding a name is a minor
bump, renaming or removing one a major bump.

**Constants.** `CONTRACT_VERSION` (`"1.0"`), `CONTRACT_MAJOR`, `CONTRACT_MINOR`,
`CONTRACT_SCHEMA` (`"vc_game_module/v1"`), `MANIFEST_SCHEMA` (`vc_game_module_manifest/v1`),
`REGISTRY_FRAGMENT_SCHEMA` (`vc_mod_capability_registry_fragment/v1`), `PINS_SCHEMA`
(`vc_game_module_pins/v1`), `GAME_ATTRIBUTE` (`"GAME"`), `MANIFEST_NAME` (`"game.json"`),
`ALLOWED_CORE_IMPORTS`, `SHARED_FORMATS_PACKAGE` (`"mod_editor.games._formats"`).

**Functions.** `accepts_contract(version)` — same major, minor ≤ the core's;
`parse_contract(version)` → `(major, minor)`; `load_manifest(package_dir)`;
`require(condition, message)` → raises `Refusal`; `contract_surface()` — the pin's input.

**Exceptions.** `ContractError` (a `ValidationError`): the package does not meet the contract.
`Refusal` (a `ContractError`): a lane declined to act; one sentence, the lane tool's own.

**Identity.** `GameIdentity(game_id, title, platform, serials, executable_sha256,
content_sha256)`. `SourceIdentity(kind, path, size_bytes, serial, executable_sha256,
serial_matches, retail_executable, headline, details)`. `SourceIdentifier` protocol:
`accepted_suffixes`, `identify(path) → SourceIdentity`, read-only.

**Lane vocabulary.** `Target(key, label, detail, budget, searchable, raw)`.
`Catalogue(schema, lane_id, source, targets, document)` with `target(key)` (refuses an unknown
key). `Edit(target_key, values, note)`. `DeclaredRange(start, length, reason)` with `end`.
`Plan(lane_id, target_keys, declared_ranges, document)` with `declared_bytes`.
`Artifact(path, sha256, kind)`. `Receipt(schema, lane_id, source, destination,
declared_ranges, document, artifacts)`. `Verdict(passed, summary, document)`.

**`Lane` protocol.** Attributes `lane_id`, `capability_id`, `surface`, `title`,
`classification`, `recipe_schema`, `validators`, `fixed_allocation`. Methods
`build_catalogue(source, *, progress=None) → Catalogue`; `check_edit(target, values) → str |
None`; `compose_recipe(edits) → Mapping` (exactly what the lane's own patcher accepts);
`plan(source, recipe, catalogue) → Plan` (dry run; raises `Refusal`); `build(source,
destination, recipe, catalogue, *, work_dir=None) → Receipt`; `verify(source, destination,
receipt) → Verdict`; `synthetic_source(work_dir) → Path`; `conformance_edits(catalogue) →
tuple[Edit, ...]`.

**Executable patches.** `CodePatch(patch_id, title, surface, parameters, host_site, note)` —
a host patch as the host catalogues it. `MipsWord(address, original, replacement)` — aligned
32-bit values; the word must change. `MipsPatch(patch_id, words, elf_identity, parameters,
note)`. `CodePatchLane(Lane)` protocol adds `patches()`, `translation(patch_id, parameters) →
MipsPatch | Refusal`, `emit_pnach(patches, crc) → str`, `verify_pnach(pnach_text, source,
expected) → Verdict` (section 11).

**Windows.** `WindowSpec(window_id, menu_label, tooltip, flag, factory, needs_studio_session)`;
`factory(parent=None, **context)` imports Qt lazily; a window that needs the Xbox studio's
session receives it as `context["facade"]`.

**Manifest.** `GameManifest(schema, game_id, package, title, platform, version, contract,
registry_fragment, allowlist_fragment, pins, product_modules, tool_modules, root,
allowlist_patterns)` with `registry_document()`, `allowlist_lines()`, `pins_document()`.

**Module.** `GameModule(contract, identity, identifier, lanes, windows, manifest, package)`
with `game_id`, `version`, `lane(lane_id)`, `window(window_id_or_flag)`.

## 5. Fragment formats

### 5.1 `game.json`

Required: `schema`, `game_id` (`^[a-z0-9][a-z0-9_]{2,63}$`), `package`
(`mod_editor.games.<directory>`), `title`, `platform`, `version` (`1.2.3[-suffix]`),
`contract` (accepted by `accepts_contract`), `registry_fragment`, `allowlist_fragment`, `pins`
(relative paths inside the package), `product_modules`, `tool_modules` (lists of module names
the runtime closure imports). Optional: `allowlist_patterns` — case-insensitive globs selecting
the game's lines in `packaging/release-allowlist.txt` (default `mod_editor/games/<dir>/*`).
Any other key is refused.

### 5.2 `registry.fragment.json`

`{"schema": "vc_mod_capability_registry_fragment/v1", "game": <games[] entry>, "surfaces":
[...], "capabilities": [...]}`. Rows are complete registry rows in the canonical registry's
own shape, sorted by id, every row's `game` the fragment's game; `surfaces` is sorted, without
repeats, and **equals** the set of surfaces the rows cover. `registry_merge.merge(core,
fragments)` appends the entry and the rows, sorts both by id, refuses a game declared twice or
a row id seen twice, and is lossless: split → merge reproduces `registry.v1.json` byte for byte.

### 5.3 `allowlist.fragment.txt`

Comment lines (`#`) then one repository-relative file per line in the release allowlist's own
grammar; duplicates and non-canonical paths are refused. `python -m mod_editor.games fragments
<game> --write` regenerates it from the canonical allowlist through `allowlist_patterns`.

### 5.4 `pins.json`

`schema`, `game_id`, then the derived counts — `capability_rows`, `surfaces`,
`hidden_disc_writers`, `save_writer_ids`, `shipped_files`, `product_modules`, `windows`,
`lanes_on_contract`, `retail_identity` — plus any keys the game adds. The game's own tests
assert them; `fragments --write` recomputes the derived ones.

## 6. Discovery and refusal

`mod_editor.games.discover(root=None) → DiscoveryReport(games, refused)`:

- scans the **resolved** games root (`/var` → `/private/var`, `RUNNER~1` → `runneradmin`)
  for subdirectories with an `__init__.py` and a `game.json`; underscore-prefixed directories
  are not games;
- imports each package and takes its module-level `GAME`;
- refuses, per package and with a sentence, a manifest that fails validation, an import that
  raises, a missing or non-`GameModule` `GAME`, a `GAME` whose manifest was not loaded from its
  own directory (compared by resolved path or `samefile`), or a game id claimed twice —
  `RefusedGame(directory, reason, title, platform, version, contract)` keeps the display fields
  read leniently from `game.json`;
- never lets one refusal stop the others.

`manifests()` reads the declarative half without importing code and **raises** on an invalid
manifest (a gate must not proceed on a half-read declaration). `load(game_id)` names the reason
when a refused game is asked for. `registry_fragments()`, `allowlist_lines()`,
`runtime_modules()` and `window_specs()` are the merge inputs a validator, `stage_release`, the
runtime closure and a File menu would read.

## 7. The chooser

`File ▸ Select other games…` (under the PS2 entries, above Quit) and `--games-chooser` open
`mod_editor.games.chooser_qt.GameChooserDialog`, drawn from the Qt-free model in
`mod_editor.games.chooser`. Columns: *Game*, *Platform*, *Module* (version), *Contract*,
*Status* (`Ready` / `Cannot load`); loadable rows first, then refused, each group by title.
The detail pane shows platform · version · contract · lane count · windows for a loadable row
and the refusal sentence for a refused one (Open disabled). Windows that
`needs_studio_session` are listed but disabled when no facade was passed. Opening goes through
`chooser.open_window`; a factory that raises becomes a `Refusal` sentence in the detail pane.
The dialog never raises out of a click and never imports a module beyond the contract.

## 8. Command line

`python -m mod_editor.games` — `list` (default), `show <id>`, `open <id> --window <id>`,
`chooser`, `conformance [--game ID] [--static-only] [--work-dir DIR]`, `pins --check|--write|
--release`, `fragments <id> --check|--write`, `new <id> --title T --platform P [--serial S]`.
The studio's `--game GAME_ID [--window WINDOW_ID]` and `--games-chooser` delegate to it.

## 9. Conformance checks

`mod_editor.games.conformance.run(game, work_dir)` — the same harness in
`tests/mod_editor/test_games_conformance.py` and the CI job `game-module contract`:

- **manifest.** `registry_fragment_exists`, `allowlist_fragment_exists`, `pins_exist`,
  `registry_fragment_reads`, `registry_fragment_valid`, `registry_fragment_game_entry`,
  `allowlist_fragment_reads`, `allowlist_files_exist`, `pins_read`, `pins_are_plain_values`,
  `runtime_modules_resolve`.
- **boundary.** `module_level_imports_stay_inside_the_contract` (section 10).
- **module.** `contract`, `identity`, `has_a_lane_or_a_window`, and per lane
  `registry_row` (a row with the lane's id, surface and classification exists in the fragment),
  `validator_declared`, `validators_exist`; per window `window.<id>`.
- **lane.<id>** on the lane's synthetic source: `synthetic_source`,
  `synthetic_source_is_a_file`, `identify`, `identify_serial`,
  `identify_synthetic_is_not_retail`, `build_catalogue`, `catalogue_has_targets`,
  `catalogue_is_retail_free`, `conformance_edits`, `conformance_edits_nonempty`,
  `check_edit_accepts_conformance_edits`, `compose_recipe`, `recipe_carries_schema`, `plan`,
  `plan_is_a_plan`, `plan_names_the_edits`, `plan_declares_ranges` (fixed allocation),
  `plan_wrote_nothing`, `plan_refuses_unknown_target`, `build`, `build_is_a_receipt`,
  `build_created_destination`, `build_left_source_unchanged`, `build_kept_size` (fixed
  allocation), `receipt_declares_ranges_or_artifacts`, `declared_ranges_inside_destination`,
  `artifacts_match_their_digests`, `every_changed_byte_is_declared` (same-size outputs),
  `verify`, `verify_passes`, `build_refuses_existing_destination`,
  `refusal_left_destination_intact`, `build_refuses_source_as_destination`,
  `refusal_left_source_intact`, `verify_fails_on_undeclared_change`.

The suite also runs the harness on a fake loadable module with zero lanes and asserts the
exact refusal sentence of a deliberately incompatible one (`vc_game_module/v9`), and it proves
the harness can fail on a lane that changes an undeclared byte.

## 10. The plugin boundary

At module level a game package may import only `mod_editor.games.contract`,
`mod_editor.core.errors`, `mod_editor.core.platform_compat`, its own package, and packages under
`mod_editor.games._formats`. Qt, `mod_editor.gui.*`, `mod_editor.core.*`, `mod_editor.studio.*`
and **a sibling game** are refused; function-level imports are lazy and allowed. Shared formats
are the sanctioned reuse path: `_formats/ps2_disc` (ISO9660 + boot identity), `_formats/ps2_elf`
(ELF headers, EE address mapping, PCSX2 CRC, pnach). In the other direction, exactly two upstream
files import the games package (section 13), each lazily and each one core-owned module.

## 11. Executable-patch lanes

A `CodePatchLane` is a `Lane` whose catalogue targets are the host's patches (`patches()`),
whose `check_edit` refuses parameters for a patch with no translation, whose `plan` resolves
every word against the user's own boot ELF (address file-backed, original word as expected),
whose `build` writes a `.pnach` and declares it as an `Artifact`, and whose `verify` re-parses
the pnach and re-reads the ELF: the CRC the file names is the ELF's PCSX2 CRC (XOR of every
32-bit word), every declared address is in the ELF, every original matches, nothing else is
declared. Delivery is emulator-side first; on-disc ELF patching is optional and separate.
`translation()` returns a `MipsPatch` or refuses with the reason. A recipe may carry
hand-authored words while a translation is proved. See `PS2_CODE_PATCH_PIPELINE.md`.

## 12. Versioning and pins

Frozen files: `mod_editor/games/contract.py`, `__init__.py`, `registry_merge.py`,
`conformance.py`, `chooser.py`, `chooser_qt.py`, `pins.py`; `tests/mod_editor/games_fakes.py`,
`test_games_contract.py`, `test_games_contract_frozen.py`, `test_games_conformance.py`,
`test_games_chooser.py`. Not frozen: `__main__.py`, `fragments.py`, `scaffold.py`, `_formats/`,
the game directories, `CONTRACT_PINS.json` and `CONTRACT_CHANGELOG.md` themselves.

The pins are **loud, not preventive**. Moving them is an event with a procedure: bump
`CONTRACT_VERSION`; add `## <version> (unreleased)` to the changelog; `python -m
mod_editor.games pins --write` (refuses when the version has not moved past a released entry,
records the pins digest under the entry); run the conformance suite; commit that alone;
`pins --release` when the version ships. `test_games_contract_frozen` fails on a pin mismatch,
on a pins file whose digest is not the one its version's entry records, and on a changelog
whose latest entry is not the current version.

## 13. Hooks in upstream files

`mod_editor/gui/studio_qt.py`: one `QAction` ("Select other games…"), one handler
`_open_game_chooser` importing `mod_editor.games.chooser_qt` lazily, one busy-state line.
`mod_editor/__main__.py`: `--game`, `--window`, `--games-chooser`, delegating to
`mod_editor.games.__main__`. Nothing else upstream names the games package; the contract test
asserts it.

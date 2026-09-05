# The game-module contract — `vc_game_module/v1`

> Normative. Contract version **1.0 (unreleased)**; the number is `CONTRACT_VERSION` in
> `mod_editor/games/contract.py`, the history is `mod_editor/games/CONTRACT_CHANGELOG.md`, and
> the files that *are* the contract are pinned in `mod_editor/games/CONTRACT_PINS.json`
> (section 12). The design rationale and the migration of the existing products are in
> `MULTI_GAME_INTERFACES_PLAN.md`; the how-to is `ADDING_A_GAME_MODULE.md`.

## 1. Scope

A **game module** is a directory `mod_editor/games/<game_id>/` that the core hosts without
knowing the game. The core discovers it, merges its fragments, proves it with a generic
conformance harness on the module's own synthetic source, gives it **a studio** — one window,
the same fourteen pages for every game — and lists that studio in the **File ▸ Select other
games…** chooser. A module reaches the core only through this contract.

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
| studio | the one window of one game: `GameModule.studio_window`, labelled `<Console> <Game> <Year> Studio` |
| page | one of the fourteen sections of a studio (section 14); a lane names one or inherits it from its surface |

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

`GAME = GameModule(contract, identity, identifier, lanes, windows, manifest, package,
studio_window)`. Construction validates the contract version, unique lane ids and capability
ids, unique window ids and flags, that every lane answers the protocol, that `studio_window`
names one of `windows`, and that the manifest agrees with the identity and the directory.
`GameModule.version` is the manifest's `version`; `GameModule.studio` is the `WindowSpec`
`studio_window` names.

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

**Pages.** `PAGE_ORDER` — the fourteen `(page_id, title)` pairs, in the studio's order.
`SURFACE_PAGES` — every capability-registry surface mapped to the page that hosts it by
default. `lane_page(lane)` — the lane's own `page` when it names one, else its surface's
default, else `textures` so a lane is always reachable somewhere. See section 14.

**Lane vocabulary.** `Field(key, kind, label, help, choices, minimum, maximum, read_only)` —
what an editor draws for one value; `kind` is one of `text`, `int`, `float`, `bool`, `choice`,
`colour_argb`, `png`, `wav`, `name_pick`, `note`. A field is the *shape*; `check_edit` stays the
only authority on whether a value fits.
`Target(key, label, detail, budget, searchable, raw, fields)`.
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

**Lane kinds.** Each is a `runtime_checkable` protocol extending `Lane`; a shell asks
`isinstance` and adds controls when the answer is yes.

- `ReadOnlyLane` adds `read_only: bool` — catalogue only, `plan`/`build`/`verify` refuse by
  contract, and the page is rendered as *inspect*. The attribute is the marker on purpose: a
  protocol with no member of its own would match every lane at runtime, so a read-only lane
  sets `read_only = True` and a reader checks the value, not merely the class.
- `ArtLane` adds `decode_png(source, target) → bytes`, `encode(source, target, png) →
  EncodedArt` (or `Refusal` naming the size it wanted) and `replacement_identity(target) → str
  | None` (the PCSX2 filename, when the game runs there). `EncodedArt(png, width, height,
  note)` is the result.
- `AudioLane` adds `decode_wav(source, target) → bytes`; the page gets Play and Export WAV.
- `CodePatchLane` is unchanged (section 11).

**Executable patches.** `CodePatch(patch_id, title, surface, parameters, host_site, note)` —
a host patch as the host catalogues it. `MipsWord(address, original, replacement)` — aligned
32-bit values; the word must change. `MipsPatch(patch_id, words, elf_identity, parameters,
note)`. `CodePatchLane(Lane)` protocol adds `patches()`, `translation(patch_id, parameters) →
MipsPatch | Refusal`, `emit_pnach(patches, crc) → str`, `verify_pnach(pnach_text, source,
expected) → Verdict` (section 11).

**Windows.** `WindowSpec(window_id, menu_label, tooltip, flag, factory, needs_studio_session)`;
`factory(parent=None, **context)` imports Qt lazily; a window that needs the Xbox studio's
session receives it as `context["facade"]`.

**Manifest.** `GameManifest(schema, game_id, package, title, platform, console, game, year,
version, contract, registry_fragment, allowlist_fragment, pins, product_modules, tool_modules,
root, allowlist_patterns, page_notes)` with `studio_label`, `page_note(page_id)`,
`registry_document()`, `allowlist_lines()`, `pins_document()`.

**Module.** `GameModule(contract, identity, identifier, lanes, windows, manifest, package,
studio_window)` with `game_id`, `version`, `studio`, `lane(lane_id)`,
`window(window_id_or_flag)`.

## 5. Fragment formats

### 5.1 `game.json`

Required: `schema`, `game_id` (`^[a-z0-9][a-z0-9_]{2,63}$`), `package`
(`mod_editor.games.<directory>`), `title`, `platform`, **`console`** (1–8 characters, no
whitespace), **`game`** (1–24 characters), **`year`** (1–8 characters, no whitespace),
`version` (`1.2.3[-suffix]`), `contract` (accepted by `accepts_contract`), `registry_fragment`,
`allowlist_fragment`, `pins` (relative paths inside the package), `product_modules`,
`tool_modules` (lists of module names the runtime closure imports). Optional:
`allowlist_patterns` — case-insensitive globs selecting the game's lines in
`packaging/release-allowlist.txt` (default `mod_editor/games/<dir>/*`); `page_notes` — a
mapping of page id to one sentence saying why that page has no lane yet. Any other key is
refused.

`GameManifest.studio_label` is `f"{console} {game} {year} Studio"` — `PS2 NFL 2K5 Studio`,
`PS2 Madden 09 Studio`. One rule names every studio: `title` and `platform` stay as the long
forms a detail pane and a receipt use, and **the label is never written out anywhere else**.
A manifest without the three keys is refused with a sentence naming them, and conformance
refuses a module whose own code or manifest contains the composed label
(`module.studio_label_is_composed_not_typed`); the generated mirrors are exempt, because their
prose comes from the canonical registry, not from the module.

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
`mod_editor.games.chooser`. **One row per module: the studio it opens.** Columns: *Studio*
(the composed label), *Status* (`Ready` / `Cannot load`), *Detail* (title, platform, module
version, contract, lane count). Rows are sorted by console, game and year. Open opens the
module's `studio_window` through `chooser.open_studio`; a refused module keeps its refusal
sentence and Open is disabled — its label is still read leniently from `game.json` so a broken
module is recognisable. A module's other windows are not listed here: they are reachable by id
through `chooser.open_window` (which `open_selected(window_id)` still uses), from the command
line, and from the studio's own Windows menu. `openable_windows(row, has_studio_session=…)`
remains the rule for a window that needs the Xbox session. The dialog never raises out of a
click and never imports a module beyond the contract.

## 8. Command line

`python -m mod_editor.games` — `list` (default; shows studio labels), `show <id>`,
`open <id> [--window <id>]` (without `--window` the module's studio opens), `chooser`,
`lane <game> <lane> <step> …` (section 8.1), `conformance [--game ID] [--static-only]
[--work-dir DIR]`, `pins --check|--write|--release`, `fragments <id> --check|--write`,
`new <id> --console C --game G --year Y --title T --platform P [--serial S]`.
The studio's `--game GAME_ID [--window WINDOW_ID]` and `--games-chooser` delegate to it.

### 8.1 The `lane` verb

```
lane <game> <lane> catalogue --source SRC --out JSON
lane <game> <lane> plan      --source SRC --recipe R --catalogue C --out JSON
lane <game> <lane> build     --source SRC --destination NEW --recipe R --catalogue C \
                             [--work-dir DIR] --receipt JSON
lane <game> <lane> verify    --source SRC --destination NEW --receipt JSON --out JSON
```

One lane step, in a child process: progress lines while it works, exactly one verdict line at
the end (`LANE_CATALOGUE ok …`, `LANE_PLAN ok …`, `LANE_BUILD ok …`, `LANE_VERIFY pass|FAIL —
…`), exit 0 or 1, and **every failure is the lane's own `Refusal` sentence on stderr, never a
traceback**. The JSON files are the contract's own values
(`vc_game_lane_catalogue/v1`, `…_plan/v1`, `…_receipt/v1`, `…_verdict/v1`) and round-trip, so
the four steps chain. The studio runs long catalogues and every build through this verb, so a
lane that raises takes a child process down and not the window.

## 9. Conformance checks

`mod_editor.games.conformance.run(game, work_dir)` — the same harness in
`tests/mod_editor/test_games_conformance.py` and the CI job `game-module contract`:

- **manifest.** `registry_fragment_exists`, `allowlist_fragment_exists`, `pins_exist`,
  `registry_fragment_reads`, `registry_fragment_valid`, `registry_fragment_game_entry`,
  `allowlist_fragment_reads`, `allowlist_files_exist`, `pins_read`, `pins_are_plain_values`,
  `runtime_modules_resolve`.
- **boundary.** `module_level_imports_stay_inside_the_contract` (section 10).
- **module.** `contract`, `identity`, `has_a_lane_or_a_window`, `studio_window` (it names one
  of `windows`), `studio_label_is_composed_not_typed` (the composed label appears in no `.py`
  or `.json` the module authors — the three generated mirrors are exempt), and per lane
  `registry_row` (a row with the lane's id, surface and classification exists in the fragment),
  `validator_declared`, `validators_exist`, `page` (`lane_page` is one of `PAGE_ORDER`, and the
  lane either names it or has a surface in `SURFACE_PAGES`); per window `window.<id>`.
- **manifest** also carries `display_fields` (console, game and year are present) and
  `page_notes_name_pages`.
- **shell.** `studio_opens` (the core shell draws the module, titled with the composed label),
  `studio_shows_every_page` (all fourteen, in order), `studio_places_every_lane`. Offscreen and
  read-only. Without PyQt5 these are one **SKIP** line naming the reason; `Check.skipped` is a
  state of its own so a green report never hides a check nobody ran.
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
`test_games_chooser.py`. Not frozen: `__main__.py`, `fragments.py`, `scaffold.py`,
`studio_qt.py`, `lane_cli.py`, `_formats/`, the game directories, `CONTRACT_PINS.json` and
`CONTRACT_CHANGELOG.md` themselves. The shell and the `lane` verb are core-owned but still
being written; they join the frozen set when the shell is finished, which is itself a pinned
edit to `pins.py`.

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

## 14. The studio and its pages

`mod_editor.games.studio_qt.GameStudioDialog(module, *, parent=None, initial_source=None)` is
the core-owned shell: the composed label, the module's title and platform, the boundary note,
and a left navigation of the fourteen pages of `PAGE_ORDER`, in the Xbox studio's order:

| page id | title | default surfaces |
|---|---|---|
| `uniforms` | Uniforms & Equipment | `uniforms` |
| `rosters` | Names, Numbers & Faces | `players_rosters`, `portraits_faces` |
| `identity` | Text & Team Identity | `colors`, `logos_cards` |
| `field_art` | Field Art & Create-Team Art | — (a lane names it) |
| `stadiums` | Stadiums | `stadiums_fields`, `models_shap_scne`, `cross_title_model_conversion` |
| `presentation` | Presentation | `scorebug_presentation` |
| `menus` | Menus & UI | `menus` |
| `crib` | The Crib | `crib_assets` |
| `audio` | Audio | `audio` |
| `gameplay` | Gameplay | `gameplay_tuning_sliders`, `catching_drops`, `cpu_ai_draft`, `mode_state_routing` |
| `playbooks` | Playbooks & Plays | `scripts_config` |
| `textures` | All Textures | `textures` |
| `saves` | Saves | `saves`, `schedules_franchise`, `franchise_restoration_cross_title` |
| `build` | Build & Share | — |

A surface two pages could claim is filed under the page that owns the whole surface; a lane
that belongs on the other one sets `Lane.page`. `page` is deliberately **not** a member of the
`Lane` protocol: making it one would refuse every lane written before the shell existed.

**Every page is always present.** A page with no lane shows one panel: `No <title> lane in
<studio label> yet.` plus the module's own `page_notes` sentence when it has one. Never a dead
button, never a hidden page. A module needs no window of its own — the scaffold points
`studio_window` at this class — and may still ship one if it must.

# Working in this repository as an assistant

Read this before editing anything. The rules are few and mechanical; the tests enforce them.

## The game-module contract

`mod_editor/games/` hosts game modules, one directory per game, behind a versioned contract:
`vc_game_module/<CONTRACT_VERSION>` in `mod_editor/games/contract.py`. The core *discovers*
modules; it never imports one by name. A module reaches the core only through
`mod_editor/games/contract.py`, `mod_editor/core/errors.py`, `mod_editor/core/platform_compat.py`
and the shared format packages under `mod_editor/games/_formats/`. The normative spec is
`docs/product/GAME_MODULE_CONTRACT.md`; the contract's own changelog is
`mod_editor/games/CONTRACT_CHANGELOG.md`.

## Frozen files — never edit without the procedure below

- `mod_editor/games/contract.py`, `__init__.py`, `registry_merge.py`, `conformance.py`,
  `chooser.py`, `chooser_qt.py`, `pins.py`
- `tests/mod_editor/games_fakes.py`, `test_games_contract.py`, `test_games_contract_frozen.py`,
  `test_games_conformance.py`, `test_games_chooser.py`

Their SHA-256s are pinned in `mod_editor/games/CONTRACT_PINS.json`, and
`tests/mod_editor/test_games_contract_frozen.py` fails on any mismatch. The pins are loud, not
preventive: an edit *can* move them, which is why the rules say when that is allowed. The
`game.json` schema is part of `contract.py`; the frozen public surface (every class, field,
protocol member and constant) is pinned by name in `test_games_contract.py`.

## When a contract change is truly needed

1. Bump `CONTRACT_VERSION` in `contract.py` — minor for an additive change, major for a rename
   or removal.
2. Add `## <version> (unreleased)` to `mod_editor/games/CONTRACT_CHANGELOG.md`: what changed,
   and whether a module written against the previous version still loads.
3. `python -m mod_editor.games pins --write` — the only sanctioned way to regenerate the pins.
   It refuses when the version has not moved past a released entry.
4. `python -m mod_editor.games conformance`, then the five contract suites.
5. Commit that alone. Never in the same commit as feature work.
6. When the version ships: `python -m mod_editor.games pins --release`.

## What a failing test means

- `test_games_contract_frozen` — you moved the contract. Put it back, or follow the procedure.
- `test_games_contract.test_public_surface_is_pinned` — a public name or field changed. Same.
- `test_games_contract.test_upstream_reaches_the_games_package_only_through_the_two_hooks` — a
  file outside `mod_editor/games/` imported the games package, or one of the two hooks
  (`mod_editor/gui/studio_qt.py`, `mod_editor/__main__.py`) imported it eagerly or named a game.
- `test_games_conformance` — a hosted module broke a rule; the check name says which, and a
  refused module is printed with its reason.
- `boundary.module_level_imports_stay_inside_the_contract` — a game imported core internals,
  Qt, or a sibling game at module level.
- `fragments` drift (`test_<game>_module`) — a module's mirrors differ from the canonical registry
  or allowlist: `python -m mod_editor.games fragments <game> --write`.

## Adding a game

`python -m mod_editor.games new <game_id> --title "…" --platform "…"`, then follow
`docs/product/ADDING_A_GAME_MODULE.md`. Everything a game needs lives under
`mod_editor/games/<game_id>/` and `tests/mod_editor/test_<game_id>_*.py`. The upstream files
that still carry per-game facts (registry rows, the allowlist, the count pins, the runtime gate's
module list) are edited by one command, `tools/registry_add_rows.py`, never by hand.

## The passive footprint of game code

- A game change edits nothing outside its own directory and its own tests.
- Import Qt only inside functions. Import the core only through the contract or `_formats`.
- Retail-free: names, offsets, lengths and digests — never payload. Fixed allocation. A writer
  ships an independent verifier that can fail. Every refusal is one sentence naming the fix.
- Text writes pass `newline="\n"`; `os.open` flags that are POSIX-only use `getattr(os, …, 0)`.
- `CONTRIBUTING.md` still applies: a capability is filed on the rung its evidence earns.

## Commits

Prose messages: what changed, and why it was wrong before. Small steps. No attribution trailers.

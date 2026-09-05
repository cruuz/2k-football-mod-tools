# Game-module contract changelog

One entry per contract version, latest first. The `pins:` line under a heading is
written by `python -m mod_editor.games pins --write` and is the digest of
`CONTRACT_PINS.json` for that version; `tests/mod_editor/test_games_contract_frozen.py`
refuses pins that do not match the entry for the current `CONTRACT_VERSION`.
`(unreleased)` marks a version still under development, whose pins may be rewritten;
`python -m mod_editor.games pins --release` drops the marker when the version ships.

## 1.0 (unreleased)
pins: 7c17bdba298fde66001ba5418affb3e811f37e94a39e6669ad5f31ac7837d1b4

First version. A game is a directory `mod_editor/games/<game>/` with a `game.json`
manifest, a registry fragment, an allowlist fragment, its own pins and a module-level
`GAME`; the core discovers it, merges its fragments, proves it with the conformance
harness on its own synthetic source, and lists it in the "Select other games…" chooser.
Frozen surface: see `docs/product/GAME_MODULE_CONTRACT.md`.

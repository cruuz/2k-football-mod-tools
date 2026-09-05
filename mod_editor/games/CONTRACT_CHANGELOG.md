# Game-module contract changelog

One entry per contract version, latest first. The `pins:` line under a heading is
written by `python -m mod_editor.games pins --write` and is the digest of
`CONTRACT_PINS.json` for that version; `tests/mod_editor/test_games_contract_frozen.py`
refuses pins that do not match the entry for the current `CONTRACT_VERSION`.
`(unreleased)` marks a version still under development, whose pins may be rewritten;
`python -m mod_editor.games pins --release` drops the marker when the version ships.

## 1.0 (unreleased)
pins: 8e240cb511d22bff6b6172a65bca84e321b8561081f423575c3a6f9f53bb4a64

First version. A game is a directory `mod_editor/games/<game>/` with a `game.json`
manifest, a registry fragment, an allowlist fragment, its own pins and a module-level
`GAME`; the core discovers it, merges its fragments, proves it with the conformance
harness on its own synthetic source, and lists it in the "Select other games…" chooser.
Frozen surface: see `docs/product/GAME_MODULE_CONTRACT.md`.

Also in 1.0, not 1.1: the executable-patch lane kind (`CodePatch`, `MipsWord`, `MipsPatch`,
`CodePatchLane`) and `Receipt.artifacts` for lanes whose output is a file rather than an
image. They were added while 1.0 was still `(unreleased)`, so no game written against a
released contract exists to be broken; a minor bump would have named a version nobody used.

Also in 1.0, for the same reason — the Game Studio shell (RC86, work package A1):

- **Three display fields in `game.json`** — `console`, `game`, `year` — and
  `GameManifest.studio_label`, which composes `<Console> <Game> <Year> Studio` from them. They
  are required: `load_manifest` refuses a manifest without them with a sentence naming them.
  `title` and `platform` stay as the long forms. Optional `page_notes` maps a page id to one
  sentence saying why that page has no lane yet. Conformance refuses a module whose own code or
  manifest spells the composed label out.
- **`GameModule.studio_window`** (required, must name one of `windows`) and `GameModule.studio`.
  The chooser now lists one row per module — its studio — and opens that window;
  `python -m mod_editor.games open <game>` opens it with no `--window`.
- **Lane vocabulary**: `Field` and `Target.fields` (the shape an editor draws; `check_edit`
  stays the rule); `ReadOnlyLane`, `ArtLane` and `AudioLane` as runtime-checkable protocols
  extending `Lane`; `EncodedArt`; `PAGE_ORDER`, `SURFACE_PAGES` and `lane_page(lane)`.
  `Lane.page` is read with `getattr` and is *not* a protocol member, so every lane written
  against 1.0 so far still answers `Lane`.
- **`python -m mod_editor.games lane <game> <lane> catalogue|plan|build|verify`** — one lane
  step in a child process, with progress lines, one verdict line, exit 0/1 and refusal
  sentences instead of tracebacks. `mod_editor/games/lane_cli.py` carries the JSON forms.
- **`mod_editor/games/studio_qt.py`** — the core shell every module gets as its studio, and the
  scaffold's default studio window. Conformance draws it offscreen (or SKIPs, named, without
  PyQt5); `Check.skipped` is a new state on the conformance report.

Also in 1.0 (RC86, work package A2) — the shell's pages, and what a lane now owes them:

- **The editor is built from `Target.fields`.** `studio_qt.FieldEditor` maps each contract kind
  to one control and back (see §14.1 of the contract doc); a blank `text` / `colour_argb` /
  `png` / `wav` field is omitted from `values`, so blank means *keep*. Conformance fails a lane
  the studio offers whose catalogued targets declare no fields
  (`lane.<id>.targets_declare_fields`) and draws them offscreen
  (`lane.<id>.fields_render`). A lane the studio does not offer SKIPs both, by name.
- **`studio_qt.OFFERED_CLASSIFICATIONS`** — only `runtime-proved`, `offline-writer-proved`,
  `extract-only` and `read-only-mapped` get controls. Any other classification gets a page
  stating the classification and the registry row's `gui.reason`, and nothing to click.
- **`Lane.scopes()` is read with `getattr`**, like `Lane.page`: a lane whose catalogue can cover
  more or less of a source offers `id`/`label`/`note` objects and the page shows a picker.
- **`ReadOnlyLane` is proved by its refusals.** `check_lane_behaviour` no longer drives a build
  a read-only lane is contracted to refuse; it proves `plan` and `build` refuse, that nothing
  was created, and that no target offers an editable field.
- **`mod_editor/games/studio_service.py`** (not frozen) — `GameStudioService(module)`: open,
  catalogue (cached per source), stage, dry-run, chained build, receipts, every step through
  the `lane` verb in a child process. Receipt schema `vc_game_studio_receipt/v1`.
- **`chooser.studio_menu_label` and `chooser.studio_window_spec`** — the label rule applied in
  one place, substituted into the module's studio `WindowSpec` wherever it is offered from
  outside the studio.
- **New shell checks**: `shell.studio_unavailable_pages_say_why`, `shell.studio_has_a_build_page`,
  `shell.studio_draws_every_offered_lane`, `shell.studio_lane_pages_have_an_editor`,
  `shell.studio_windows_menu_lists_the_side_windows`.
- **`mod_editor/games/studio_qt.py` joins the frozen set**: a game now depends on the shape of
  the page it is drawn on, so it moves through the version procedure like the rest.

A module written against 1.0 before this entry no longer loads unchanged: it must add the three
manifest fields and a `studio_window`. That is a breaking change to an *unreleased* version,
taken deliberately — `nfl2k5_ps2` is the only module in existence, the scaffold writes the new
shape, and a game without a studio has nowhere to appear.

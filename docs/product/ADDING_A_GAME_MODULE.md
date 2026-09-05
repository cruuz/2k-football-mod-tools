# Adding a game module — the exact steps for a PR

This is the how-to. The contract itself is `GAME_MODULE_CONTRACT.md`; the reasoning is
`MULTI_GAME_INTERFACES_PLAN.md`. Everything a game needs lives under
`mod_editor/games/<game_id>/` and `tests/mod_editor/test_<game_id>_*.py`; the upstream files
that still carry per-game facts today are edited by one command (step 8), never by hand.

## 0. Before you start

- Python 3.11+, `PyQt5 Pillow` installed, the suite runnable as `CONTRIBUTING.md` says.
- A **game id**: lowercase, digits and underscores, e.g. `madden08_ps2`, `espn_nba2k5_ps2`.
- The three **display fields** the studio label is composed from: `console` (1–8 characters, no
  whitespace), `game` (1–24), `year` (1–8, no whitespace) — `PS2` / `Madden` / `08` gives
  **PS2 Madden 08 Studio**. Never write the label itself anywhere; conformance refuses a module
  that does.
- The game's **identity**: disc serial(s), the retail executable digest, the whole-image digest
  if there is one. Hashes only; nothing else about the game enters the repository.
- For every lane you plan: a **catalogue tool**, a **patcher** and an **independent verifier**,
  the trio every shipped PS2 lane has, plus a **synthetic source** the lane can be proved on
  without game data. If a lane cannot build a synthetic source, it is not ready for a PR.

## 1. Scaffold

```bash
python -m mod_editor.games new madden08_ps2 --title "Madden NFL 08 (USA, PlayStation 2)" \
    --platform "PlayStation 2" --console PS2 --game Madden --year 08 --serial SLUS-21638
python -m mod_editor.games conformance --game madden08_ps2      # passes on day one
PYTHONPATH=. python tests/mod_editor/test_madden08_ps2_module.py
python -m mod_editor.games open madden08_ps2                    # its studio, fourteen pages
```

The scaffold writes `mod_editor/games/madden08_ps2/` — `__init__.py` (`GAME`), `__main__.py`,
`game.json`, an **example lane** over a synthetic slot-file format (`example_lane.py`, its two
validators), `registry.fragment.json` (one complete placeholder row), `allowlist.fragment.txt`,
`pins.json` — and `tests/mod_editor/test_madden08_ps2_module.py`. The example lane is a teaching
template: delete it (and its row) before the first real row; its summary says PLACEHOLDER
everywhere so it can never be mistaken for a capability.

The module's `studio_window` points at the **core shell**
(`mod_editor.games.studio_qt.GameStudioDialog`), so the new game already has all fourteen
pages, each saying honestly what it has and has not. You write lanes; the pages appear.

## 2. Identity

Fill `IDENTITY` in `__init__.py`: serials, `executable_sha256`, `content_sha256`. Use a shared
identifier when one exists (`mod_editor/games/_formats/ps2_disc.Ps2DiscIdentifier(IDENTITY)`
for a PS2 disc) or write one implementing `SourceIdentifier`: read-only, refuses with a
sentence, never guesses. Put the same digests in the fragment's `games[].retail_identity`.

## 3. Lanes

One lane = one registry row. Wrap the trio without changing it, the way
`mod_editor/games/nfl2k5_ps2/__init__.py` wraps the uniform-colour tools:

- `build_catalogue(source)` → the tool's catalogue, verbatim, as `Catalogue.document`; targets
  with a `key` the recipe takes, a `budget` in the user's words, and the `fields` an editor
  draws (`Field(key, kind, label, help, …)`; `check_edit` is still the only rule);
- `check_edit(target, values)` → the inline refusal, or `None`;
- `compose_recipe(edits)` → **exactly** the document the patcher's own parser accepts;
- `plan` / `build` / `verify` → the tool's dry run, apply and independent verifier; every
  refusal re-raised as `Refusal(str(exc))`, never re-worded;
- `synthetic_source(work_dir)` and `conformance_edits(catalogue)` → what CI proves the lane on.

Set `fixed_allocation=True` when the destination must keep the source's exact size (declare
byte ranges); `False` for a lane that writes files (declare `Receipt.artifacts`). Put the lane's
`validate_<lane>.sh/.bat` under the package (CRLF for `.bat`, executable LF for `.sh`) and name
them in `validators`; the registry row's `validation_command` runs one of them.

For executable patches use the `CodePatchLane` shape — see `PS2_CODE_PATCH_PIPELINE.md`. For
texture art implement `ArtLane` (`decode_png`, `encode`, `replacement_identity`) and for sounds
`AudioLane` (`decode_wav`); a lane that only catalogues declares `read_only = True` and answers
`ReadOnlyLane`. Each one gives the shell's page its controls and nothing else does.

**Which page a lane lands on** comes from its surface (`SURFACE_PAGES`); set `Lane.page` to one
of `PAGE_ORDER`'s ids when the default is wrong (a field-art lane on the `textures` surface
sets `page = "field_art"`). Conformance refuses a lane whose page is not a studio page. If a
page has no lane yet, say why in `game.json`'s `page_notes`: one sentence, shown on the page
under the core's own.

**Give every target its `fields`.** They are what the shell's editor draws, and a writer whose
targets declare none fails conformance rather than showing an empty panel a user has to guess
at. Pick the kind that says what the value *is* — `colour_argb` for a packed colour word,
`wav` for a sound slot, `float` for a position, `choice` when the tool takes a fixed set,
`note` for something the page should say but nobody types — and let `check_edit` stay the only
rule about whether a value fits. A blank `text`, `colour_argb`, `png` or `wav` field is left
out of `values`, so it means *keep what is there*; `int`, `float`, `bool` and `choice` always
send. Mark a value the user may see but not change `read_only=True`.

**Scopes are optional.** A lane whose catalogue can cover more or less of a source (one proved
scene, or every scene) offers `scopes()` returning objects with `id`, `label` and `note`; the
page shows a picker only when there is more than one. It is read with `getattr`, so a lane that
has one scope says nothing.

**A lane the registry has not classified is not drawn.** Only `runtime-proved`,
`offline-writer-proved`, `extract-only` and `read-only-mapped` get controls; anything else gets
a page stating the classification and that row's `gui.reason`, and the field checks SKIP by
name until the row earns a classification the studio offers.

Every step of a lane is runnable without a window, which is how to develop one:

```bash
python -m mod_editor.games lane madden08_ps2 example.slots catalogue --source in.slot --out c.json
python -m mod_editor.games lane madden08_ps2 example.slots build --source in.slot \
    --destination new.slot --recipe recipe.json --catalogue c.json --receipt receipt.json
python -m mod_editor.games lane madden08_ps2 example.slots verify --source in.slot \
    --destination new.slot --receipt receipt.json --out verdict.json
```

## 4. The studio, and any other windows

`GameModule.studio_window` names the window the chooser opens and the one
`python -m mod_editor.games open <game-id>` opens: keep it pointed at the core shell unless the
game genuinely needs a window of its own. Expose any further window as a `WindowSpec` whose
factory imports Qt **inside the function**; a window that works on the Xbox studio's open
project sets `needs_studio_session=True` and reads `context["facade"]`. The chooser lists
studios, not windows — a second window is reached with `python -m mod_editor.games open
<game-id> --window <window-id>` and from the studio's own Windows menu, which lists every
window except the studio itself. Do not add File-menu entries or CLI flags upstream, and do not
type the studio label into a menu label: the core composes it (`chooser.studio_menu_label`) and
substitutes it wherever the studio is offered from outside, so your studio window's own
`menu_label` should say what that window is called *inside* the studio ("Disc Studio…").

## 5. Fragments and pins

- `registry.fragment.json`: complete rows in the canonical registry's shape (copy an existing
  row of the same classification as a template; `mod_editor/capabilities/validate_registry.py`
  is the authority on keys and the classification ↔ `(operation, gui.mode)` pairs), sorted by
  id; `surfaces` = exactly the surfaces the rows cover. File each row on the rung its evidence
  earns (`CONTRIBUTING.md`).
- `allowlist.fragment.txt`: every file the game ships. Set `allowlist_patterns` in `game.json`
  if the game's files do not all live under its directory.
- `pins.json`: `python -m mod_editor.games fragments <game_id> --write` recomputes the derived
  counts; add your own keys beside them.

## 6. Tests

`tests/mod_editor/test_<game_id>_module.py` (scaffolded) runs the harness and the fragment
check. Add lane tests in the style of `tests/mod_editor/test_games_ps2_code_patches.py`: the
tool's refusal sentences verbatim, a build that verifies, a tampered output that fails.
CI globs `tests/mod_editor/test_*.py`; nothing in `.github/` changes.

## 7. Prove it

```bash
python -m mod_editor.games conformance --game <game_id>     # every check named
python -m mod_editor.games fragments <game_id> --check
python -m mod_editor.games                                 # the studio is listed and Ready
python -m mod_editor.games open <game_id>                  # the studio opens alone
python -m mod_editor.games open <game_id> --window <id>    # any other window opens alone
```

## 8. What still touches upstream files today — one command

Until the validator derives games and coverage from fragments (plan §5), a game PR appends
its rows to the canonical registry, its files to the release allowlist, its modules to the
runtime gate, and moves the thirteen count pins. `tools/registry_add_rows.py` does all of it,
computing every edit and asserting it matches exactly once before writing anything:

```bash
# rows of a game the registry already knows (e.g. more PS2 rows)
python3 tools/registry_add_rows.py --game nfl2k5_ps2 \
    --row rows/nfl2k5ps2.new_row.json [--row ...] \
    --widen <surface-not-yet-covered-by-this-game> \
    --module mod_editor.games.nfl2k5_ps2 --module mod_editor.games.nfl2k5_ps2.code_patches \
    --allowlist-fragment mod_editor/games/nfl2k5_ps2/allowlist.fragment.txt [--dry-run]

# a game id the registry has never seen
python3 tools/registry_add_rows.py --game madden08_ps2 \
    --new-game rows/madden08_ps2.games-entry.json --display-name "Madden NFL 08 (PS2)" \
    --row rows/madden08_ps2.saves.roster.json --widen saves \
    --allowlist-fragment mod_editor/games/madden08_ps2/allowlist.fragment.txt \
    --module mod_editor.games.madden08_ps2

# then keep the mirrors in step
python -m mod_editor.games fragments <game_id> --write
python3 mod_editor/capabilities/validate_registry.py --skip-file-checks
```

`--new-game` also adds the `GameId` member, the `_game_id` map entry, the `_validate_games`
set entry, `GAMES` and the games-count pin, both schema enums and `project.schema.json`, and
rewrites the coverage table so surfaces every established game covers are not demanded of the
newcomer. `KNOWN_FINGERPRINTS` in `mod_editor/core/sources.py` stays manual (its kinds are
game-specific). The RC bump (`--rc OLD NEW --changelog-section FILE --status-heading TEXT`)
is the release owner's call, not the game PR's. Nothing about a game touches
`mod_editor/gui/studio_qt.py` or `mod_editor/__main__.py`; if a PR does, it is wrong.

## 9. The PR description

Say **what you proved and how**, and what you did not prove — the conformance summary, the
lane validators' PASS lines, and the classification each row earned. "Not tested in game" is
what is being asked for when that is the truth.

## 10. Checklist

- [ ] no file outside `mod_editor/games/<game_id>/`, `tests/mod_editor/test_<game_id>_*.py`
      and the outputs of `tools/registry_add_rows.py`
- [ ] `python -m mod_editor.games conformance --game <game_id>` all PASS
- [ ] `python -m mod_editor.games fragments <game_id> --check` OK
- [ ] every lane has a synthetic source, a known-good edit, an independent verifier that fails
      on a tampered output, and refusal sentences that name the fix
- [ ] `console`, `game` and `year` in `game.json`; the composed label typed nowhere
- [ ] every lane lands on the right page, and every page without one has a `page_notes` sentence
      or is honestly empty
- [ ] the example lane and its row are gone
- [ ] no game data: hashes, offsets, lengths, names only
- [ ] `python -m mod_editor.games pins --check` untouched (game files are not frozen)

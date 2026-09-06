# Adding a game module — the exact steps for a PR

This is the how-to. The contract itself is `GAME_MODULE_CONTRACT.md`; the reasoning is
`MULTI_GAME_INTERFACES_PLAN.md`. Everything a game needs lives under
`mod_editor/games/<game_id>/` and `tests/mod_editor/test_<game_id>_*.py`; the upstream files
that still carry per-game facts today are edited by one command (step 8), never by hand.

`docs/product/MODULE_AGENT_CHARTER.md` is the standing rules that go with these steps -- the
gates, the retail-free rule, the shared-file rule, where the measured facts already live, and
the shape of the report. Read it once; this page assumes it.

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
byte ranges); `False` for a lane that writes files (declare `Receipt.artifacts`). The lane's
validator is **not** a new script: add the lane to `mod_editor/games/<game_id>/validators.json`
(the sources it compiles, the self-tests it runs, whether it needs the conformance harness) and
write the two thin wrappers `tools/validate_<game_id>_<lane>.sh/.bat` that call
`tools/validate_game_lane.py --game <game_id> --lane <lane>` (CRLF for `.bat`, executable LF for
`.sh`). The pass token is derived as `<GAME_ID>_<LANE>_VALIDATION_PASS`; the registry row's
`validation_command` runs the `.sh`. `python3 tools/validate_game_lane.py --game <game_id> --all`
runs every lane with the harness once instead of once per lane.

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

### 3a. Before you write a lane: is it already written?

`mod_editor/games/_formats/` holds the **formats** — a reader that knows a
container and nothing about a game. `mod_editor/games/_lanes/` holds the layer
above: the **lane shapes** two games on the same stack would otherwise write
twice. A game composes a lane base exactly as it composes a format package, and
still never imports a sibling game.

| base | what it is | instantiated by |
|---|---|---|
| `_lanes/tdb_records.TdbRecordLane` | one record of one EA TDB table inside a container member, catalogue to independent verdict | Madden 09 team data; NCAA 09 rosters, identity, playbooks |
| `_lanes/terf_art.TerfArtLane` / `TerfArtWriteLane` | an `MMAP` texture member: catalogue, decode, checked import, PCSX2 identity, export, disc write-back | Madden 09 ×5 rows, NCAA 09 ×6 rows |
| `_lanes/text_banks.TextBankLane` | a `TEXT` string slot, rewritten in place inside its own allocation | Madden 09 and NCAA 09 menus |
| `_lanes/preload_coherence` | rewrite every stale `QL01` cache copy or refuse; and re-check from the destination | every writer on this stack |
| `_lanes/iso_tools` | the ISO writer and verifier import shims and the declared-range helpers | every writer that rebuilds an image |
| `_lanes/synthetic_art` | the `MMAP` fixtures CI proves an art lane on | both games |

**What a base takes as data**, and therefore what your module still writes:

* `discs` — your own `containers` module. The protocol a base is entitled to
  use is written down in `_lanes/__init__.py`;
* the lane's identity — capability id, lane id, surface, page, title, the three
  schema strings, and the two validators;
* **the field map, or the container list.** This is the half that never ports.
  Madden 09 and NCAA Football 09 share 37 `PLAY` field names out of 110 and 86;
  NCAA's ratings are five bits where Madden's are seven; NCAA's `PBPL` has no
  play name where Madden's does. Every one of those is a line in a tuple, and
  none of them is a line of logic.

**How much this actually saves**, measured on the second game [M]. NCAA
Football 09's three EA TDB record rows are 452, 357 and 344 lines of field map
and page prose, against the **1,074-line** lane each would otherwise have had to
be; its six art rows are 259 + 348 lines against **1,651**; its text row is 274
against **841**. Madden 09's own three shrank the same way in the same commit:
team data 1,266 → 511, text 960 → 223, uniform art 1,753 → 243. The bases are
3,566 lines that are now written once and tested once, and every one of them was
already written — the move added no behaviour, it moved eleven callers onto one
implementation.

**When to leave a lane concrete.** A base that one game instantiates is a base
in name. If the second game's lane differs in more than its field map — a
different container format, a different write bound, a different verdict — write
it concrete and say why in the module document. That is a smaller cost than a
base with a flag for every difference.

**If a base needs to change for your game**, change the base and re-run the
*other* game's conformance and suites before you commit. `_lanes` is upstream of
every module that imports it, and a base whose second caller quietly broke its
first is worse than two copies.


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

## When a module is finished — the shipping standard

A game module ships when it is **feature complete**, not when its first lanes work. The owner's rule
(2026-09-06): the standard set by the first two modules is the standard for every module after them.
"Complete" means all of the following, and the module's document states each one with its evidence:

1. **Every page has its answer.** Each of the shell's fourteen pages either carries a lane at the
   highest rung the disc's format permits, or states a *measured* reason the disc cannot support it
   (a format with no data on the disc, a concept the game does not have). "Not built yet" is not a
   reason; it is a gap.
2. **Every writer is proved twice.** Offline: an independent verifier that imports none of the writer
   re-derives the edit from the built image and checks every byte outside the declared ranges
   (`offline-writer-proved`). In game: the edit seen on screen or heard, on the rig, with the boot
   recorded as evidence (`runtime-proved`). A writer that has only the first is shipped as such and
   says so; the module is not complete until the second exists for every writer the format permits.
3. **Art round-trips.** Textures decode to PNG, edited PNGs encode back, the encoder round-trips real
   members byte for byte where the format allows, and the PCSX2 replacement identities exist (from a
   captured texture dump) so the pack route names its files. Both the disc route and the pack route.
4. **Rosters, team data and text** have writers with the four database CRCs proved against the disc's
   own databases before any write is offered.
5. **Audio, stadiums, playbooks and gameplay patches** have lanes at the rung their formats permit,
   with the encoder or writer built when the format is documented, and a measured statement when it
   is not. The executable-patch lane carries at least the translations the community already ships,
   verified against the boot executable.
6. **Validators run in a shipped tree** on Linux and on a real cmd.exe; the portable build's smoke
   passes on Windows; the module's registry rows carry evidence paths that exist.
7. **Nothing is claimed above its proof.** `unknown` rows stay hidden; `extract-only` never becomes
   `runtime-proved`; a module doc lists what still needs a boot.

A pull request that adds a module lists this checklist with a yes, a no with the reason, or a
measured "not applicable" for every line.

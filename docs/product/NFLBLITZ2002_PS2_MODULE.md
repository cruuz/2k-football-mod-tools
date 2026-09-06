# NFL Blitz 2002 (PlayStation 2) — module capability summary

This page summarises what the `nflblitz2002_ps2` game module offers on each Studio
page and where it stops. It is a capability summary, not a format study, and it
carries no findings of its own. To use any of it you supply your own legally
obtained USA PlayStation 2 disc image of NFL Blitz 2002 (SLUS-20051); the tool
bundles no game files, no BIOS, no saves and no emulator binaries.

## Opening it

Start Mod Studio and choose **NFL Blitz 2002 (PS2)** from *Select other games…*, or open it
straight from a terminal:

```
python -m mod_editor --game nflblitz2002_ps2
```

Point it at your own disc image. The module checks that the image is the release it
supports and refuses by name if it is not, so a wrong disc costs you a sentence rather
than a bad build.

## Before you build anything

**Every writer in this module is proved offline and has never been seen in a running
game.** Precisely: the rebuilt image is checked byte for byte by a verifier that shares
no code with the writer, each edit is confirmed to land inside the range its capability
row declares, and every other byte of the image is confirmed unchanged. What that does
not cover is the game itself — nobody has booted the result. If you load a rebuilt image
in an emulator or on hardware you are the first person to do so, and a crash, a missing
texture or a wrong string is a real possibility rather than a surprise. Please report
what you see.

A build always writes a **new** image, to a destination that does not already exist. The
disc image you supply is opened for reading and is never modified, so a bad build costs
you the output file and nothing else.

## What the module edits

The module identifies the disc, opens it for reading only, and offers four kinds
of work:

- **Text tables.** Three of the disc's plain-text tables — the field table, the
  crowd tables and the trivia banks — are presented as line editors, and an
  edited line is written back into the space it already occupies.
- **Roster names.** Player names are editable. The numeric columns beside them
  are listed but not editable.
- **Texture export.** Team and menu texture dictionaries are previewed and
  exported to PNG. Nothing is imported.
- **Inventories.** Two view-only tables: the disc's texture dictionaries, and
  its camera paths and containers.

An edit produces a new disc image. The image you supply is never modified.

## Studio pages

| Studio page | Registry row | Classification | What it does | What it will not do |
|---|---|---|---|---|
| Gameplay | `nflblitz2002ps2.gameplay.field_table` | `offline-writer-proved` | Line editor over the disc's field table, each line bounded by the space it already owns. | Add, remove or lengthen a line; a value that does not fit is refused by name. |
| Text & Team Identity | `nflblitz2002ps2.identity.crowd_tables` | `offline-writer-proved` | Line editor over the crowd tables. | Reach any team identity held outside those tables, or lengthen a line. |
| Names, Numbers & Faces | `nflblitz2002ps2.rosters.player_names` | `offline-writer-proved` | Name editor over the roster, each name bounded by the field it already owns. | Edit ratings, numbers or faces — those columns are listed but not measured, so no editor is offered. |
| Playbooks & Plays | `nflblitz2002ps2.playbooks.trivia_banks` | `offline-writer-proved` | Line editor over the trivia banks. | Expose play or formation data; the module offers no play editor. |
| Uniforms & Equipment | `nflblitz2002ps2.uniforms.team_textures` | `extract-only` | Preview and Export PNG for the team texture dictionaries. | Import or write back a raster; the page states in its own words why. |
| Menus & UI | `nflblitz2002ps2.menus.screen_textures` | `extract-only` | Preview and Export PNG for the screen texture dictionaries. | Import or write back a raster. |
| All Textures | `nflblitz2002ps2.textures.dictionary_inventory` | `read-only-mapped` | Inventory table of every texture dictionary on the disc. | Edit or export from this page; it is a table and no editor. |
| Presentation | `nflblitz2002ps2.presentation.camera_paths` | `read-only-mapped` | Inventory table of the disc's camera paths and containers. | Edit a camera; the page states in its own words that a camera record's fields are not measured. |

## Pages that are deliberately empty

- **Field Art** — the disc carries no create-team or field-art container. Its
  field data is a single text table, edited on the Gameplay page rather than
  duplicated here; every other art member is reached from one of the three
  texture pages.
- **Stadiums** — stadium geometry is held in a different kind of stream from the
  texture dictionaries this module reads, and reading it would need a reader the
  module does not ship. Those members are counted and named on the Presentation
  inventory, and no stadium editor is offered.
- **The Crib** — an ESPN NFL 2K5 feature and not an NFL Blitz concept, so the
  page stays empty here on purpose.
- **Audio** — all of the disc's audio is a single sound-bank member whose format
  is owned by another module in this repository. This module names it in the
  inventory and reads none of it.
- **Saves** — a save is not the disc. The disc's save icons are dashboard art,
  not saves, and no memory-card save for this game has been measured by this
  project.

## Limits

- The image you supply is opened for reading only; the module writes a rebuilt
  image to a destination that must not already exist, and a refusal leaves no
  destination behind.
- Every edit is fixed allocation: a value fits the line or field it is given or
  is refused by name. Nothing moves, nothing changes length, and the rebuilt
  image is the same length as the source.
- A value carrying a line break or an embedded terminator is refused.
- The export pages are one-way: preview and PNG out, no import, and nothing is
  written to the disc, to a save or to the emulator.
- The replacement identity an exported raster carries for use with emulator
  texture replacement is derived from the raster itself and is never claimed to
  have been confirmed; no texture dump of this disc exists in this project.
- The two inventories accept no value to write at all.
- The listing pages cap how many rows they enumerate as targets, while the
  totals they report stay complete.
- Ratings, jersey numbers, faces and camera fields stay read-only because they
  have not been measured — the module offers an editor only where it can state
  what a value means.

## Evidence and status

Each row in the table above is a claim recorded in the shipped capability
registry, on the terms set out in `GAME_MODULE_CONTRACT.md`. The proof of each
claim is the module's own tests — `tests/mod_editor/test_nflblitz2002_ps2_lanes.py`
and `tests/mod_editor/test_nflblitz2002_ps2_module.py` — together with the
`tools/validate_nflblitz2002_ps2_*.sh` wrappers, which check a rebuilt image
independently of the code that wrote it. The repository stays retail-free: no
line, name, pixel or palette entry from any disc is stored here, and the tests
exercise the whole path against a synthetic disc the module builds from the
formats' rules.

No row in this module is `runtime-proved`. No rebuilt image has been booted, and
nothing described on this page has been confirmed in game.

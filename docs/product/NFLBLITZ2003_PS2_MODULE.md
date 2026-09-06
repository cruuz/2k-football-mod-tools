# NFL Blitz 2003 (USA, PlayStation 2) — module capability summary

This page is the capability summary for the `nflblitz2003_ps2` game module: what each
Studio page offers, what it refuses, and how far each claim has been proved. It is a
reference for the shipped module, not a study of the disc.

You supply the disc. The module reads a legally obtained USA PlayStation 2 image of
NFL Blitz 2003 (serial SLUS-20474). No game files, BIOS, saves or emulator binaries
are bundled with the tool, and no content from any retail disc is stored in this
repository.

## Opening it

Start Mod Studio and choose **NFL Blitz 2003 (PS2)** from *Select other games…*, or open it
straight from a terminal:

```
python -m mod_editor --game nflblitz2003_ps2
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

The module works off the disc image directly, and editing is confined to text and
names that already sit in it: the crowd tables, the field table, the trivia banks and
the roster's player names.

Every edit is written inside the space the line or field already occupies. The member
goes back where it lies, no member changes length, and the rebuilt image is exactly as
long as the source. Where the disc records a member's checksum in more than one place,
all of those places are updated together or the edit is refused outright.

Writing always produces a new file: the source image is opened read-only, the
destination must not already exist, and a refusal leaves no destination behind.

Everything else on offer is inspection. Textures are decoded and exported to PNG;
cameras and texture dictionaries are inventoried. Nothing is written back into art,
geometry or audio.

## Studio pages

| Studio page | Registry row | Classification | What it does | What it will not do |
| --- | --- | --- | --- | --- |
| Gameplay | `nflblitz2003ps2.gameplay.field_table` | `offline-writer-proved` | Line editor over the disc's field table, each line bounded by its own span. | Add, remove or lengthen a line; an oversized value is refused by name. |
| Text & Team Identity | `nflblitz2003ps2.identity.crowd_tables` | `offline-writer-proved` | Line editor over the crowd tables. | Change any line's length, or accept a line break or an embedded NUL. |
| Playbooks & Plays | `nflblitz2003ps2.playbooks.trivia_banks` | `offline-writer-proved` | Line editor over the trivia banks. | Edit plays or formations — the trivia banks are the only row registered for this page. |
| Names, Numbers & Faces | `nflblitz2003ps2.rosters.player_names` | `offline-writer-proved` | Name editor over the roster's player records. | Edit ratings or any numeric column; those are not measured. A name too long for its field is refused, naming the limit. |
| Uniforms & Equipment | `nflblitz2003ps2.uniforms.team_textures` | `extract-only` | Preview and Export PNG for the team texture dictionaries. | Import. No raster is written back, and the page states in its own words why. |
| Menus & UI | `nflblitz2003ps2.menus.screen_textures` | `extract-only` | Preview and Export PNG for the screen textures. | Import. The lane refuses every value offered for writing. |
| Presentation | `nflblitz2003ps2.presentation.camera_paths` | `read-only-mapped` | Lists the camera paths and the containers inventoried alongside them. | Edit a camera; a camera record's fields are not measured. |
| All Textures | `nflblitz2003ps2.textures.dictionary_inventory` | `read-only-mapped` | Inventory of every texture dictionary on the disc, with sibling counts for members this module does not open. | Anything else — it is a table with no editor. |

## Pages that are deliberately empty

- **Field Art** — the disc carries no create-team or field-art container; its field
  data is a single text table already edited on the Gameplay page rather than
  duplicated here, and every other art member is reached from Uniforms & Equipment,
  Menus & UI or All Textures.
- **Stadiums** — stadium geometry lives in model streams that need a different reader
  from the texture one this module ships, so those members are counted and named on
  the Presentation inventory and no stadium editor is offered.
- **The Crib** — a feature of another franchise and not an NFL Blitz concept, so the
  page stays empty here on purpose.
- **Audio** — all of this disc's audio is a single Midway sound bank whose format is
  owned by another module in this repository; this module names the member in an
  inventory and reads none of it.
- **Saves** — a save is not the disc, and no memory-card save for this game has been
  measured by this project.

## Limits

- Art is export-only: the texture lanes refuse every value offered for writing, so
  nothing drawn ever returns to the disc.
- A PCSX2 replacement identity is derived from a raster's own bytes and is never
  claimed to have been confirmed; no texture dump of this disc exists in this project.
- Cameras are listed, not understood: a record's fields are not measured, which is why
  the Presentation page is a table and not an editor.
- Roster editing stops at names, because the numeric columns are not measured.
- Text edits are bounded by the span they are given; a value that does not fit is
  refused naming the byte count, as are line breaks and embedded NULs.
- The inventories cap how many rows they list while their totals stay complete, so a
  very large set is summarised rather than enumerated in full.
- Audio and model geometry are named and counted but never opened; both would need
  readers this module does not ship.
- No retail content lives in this repository — no line, name, pixel or palette entry
  from any disc.

## Evidence, and what has not been proved

The registry row is the claim. Its classification, its GUI mode and its constraints are
what the module promises for that page, and the vocabulary used above —
`read-only-mapped`, `extract-only`, `offline-writer-proved` — is defined in
`GAME_MODULE_CONTRACT.md`; `ADDING_A_GAME_MODULE.md` covers how a module registers
pages like these.

The proof is the module's tests — `tests/mod_editor/test_nflblitz2003_ps2_lanes.py`
and `tests/mod_editor/test_nflblitz2003_ps2_module.py` — together with the
`tools/validate_nflblitz2003_ps2_*.sh` wrappers, which run the same paths end to end.
The verifier behind them imports none of the patcher: it re-derives everything from the
rebuilt image's own bytes, requires every untouched member to come back byte-identical,
requires every changed member's checksum to agree everywhere the disc keeps it, and
re-parses a rewritten roster to confirm each record still sits in its own block. CI
exercises the whole path against a synthetic image the module builds from the formats'
rules, so none of it depends on retail content.

No row in this module is classified `runtime-proved`. Nothing described on this page
has been confirmed by booting the game: every writer is `offline-writer-proved` and no
more, meaning a rebuilt image has been verified offline and never on hardware or in an
emulator.

# MVP Baseball 2005 (PlayStation 2) — module capability summary

This page is the capability summary for the MVP Baseball 2005 (PlayStation 2)
game module: what each page of its Studio can change, what it refuses, and how
far each claim has been taken. It is not a study of the disc's formats. The
user supplies a legally obtained USA-release disc image of the title
(SLUS-21135); the tool bundles no game files, no BIOS, no saves and no
emulator binaries. Every writer on this disc produces a **new** image and
never touches the source — naming the source as the destination is refused.

MVP Baseball is a baseball title in a tool whose other modules are football
games. It sits on the same game-module contract as all of them
(`docs/product/GAME_MODULE_CONTRACT.md`, and
`docs/product/ADDING_A_GAME_MODULE.md` for how a module is added), so the
pages, the classifications and the refusal wording read the same here; only
the subject matter is different.

## Opening it

Start Mod Studio and choose **MVP Baseball 2005 (PS2)** from *Select other games…*, or open it
straight from a terminal:

```
python -m mod_editor --game mvp05_ps2
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

The module works entirely off the disc. It reads the roster and tuning tables
that live on it as text and lets a modder change any cell of them; it replaces
the menu and in-game strings inside the spans they already occupy; it exports
and re-imports the palettised textures of the kit a player actually wears, of
the ballparks, of the presentation overlays and of the menu widgets; and it
plays, exports and replaces the standalone audio streams. Alongside those
writers it publishes three read-only inventories — the uniform preview
swatches, the portrait and head banks, and one table of every image bank on
the disc — so that what cannot be edited is still visible and named rather
than silently missing.

## Studio pages

| Studio page | Registry row | Classification | What it does | What it will not do |
| --- | --- | --- | --- | --- |
| Uniforms & Equipment | `mvp05ps2.uniforms.kit_textures` | `offline-writer-proved` | Exports and re-imports the palettised textures of the worn kit — caps and helmets, sleeves, batting gloves, wristbands, the low-detail kit, and every letter and digit the game composites into a nameplate and a squad number. Each bank names its club by rule rather than by a table this repository carries. | Will not touch the high-detail jersey, the trousers, the shoes or the heads: those use the compressed texture format this project has not decoded. Direct-colour stubs export only. |
| Uniforms & Equipment | `mvp05ps2.uniforms.kit_banks` | `read-only-mapped` | Lists the uniform preview swatches with their sizes, each carrying the measured reason it is not drawn, above the writer row. | No preview, no export, no edit. |
| Names, Numbers & Faces | `mvp05ps2.rosters.database_tables` | `offline-writer-proved` | Edits any cell of the roster tables — player attributes, pitchers, roster assignments, team rows, and the batting, pitching, career, organisation and manager records — re-packing each table into the slot its entry already owns. | Will not accept a comma or a line break in a value, will not change a column's kind, and will not let an entry grow past its slot or move. |
| Names, Numbers & Faces | `mvp05ps2.rosters.face_banks` | `read-only-mapped` | Lists the portrait and head banks with their sizes, beside the roster writer. | Nothing in them decodes, so nothing is drawn, exported or written. |
| Text & Team Identity | `mvp05ps2.identity.team_tables` | `offline-writer-proved` | Edits the team, organisation and manager rows — club names, cities and abbreviations among their columns. | Will not edit colours: this disc's team table carries no colour column by name, and the page says so rather than inventing one. |
| Text & Team Identity | `mvp05ps2.identity.ui_strings` | `offline-writer-proved` | Replaces a menu or in-game string inside the span it already occupies, across the three text files the game ships. | A replacement longer than its span is refused, naming the characters to cut; a shorter one is padded. |
| Field Art & Create-Team Art | `mvp05ps2.field_art.banks` | `read-only-mapped` | Lists the field art and the ballpark-builder archives with their sizes and the measured reason nothing is drawn. | No preview, no export, no edit; none of these images has a texture-replacement name, for the same reason none is drawn. |
| Stadiums | `mvp05ps2.stadiums.park_textures` | `offline-writer-proved` | Previews, exports and re-imports the palettised park textures across every park archive, and says of each texture whether its replacement name was measured against a texture dump or computed from its own bytes. | Crowd banks and park menu art are listed only. The per-park geometry objects have no reader here. |
| Presentation | `mvp05ps2.presentation.overlay_textures` | `offline-writer-proved` | Exports and re-imports the palettised overlay art on the same controls as the stadiums page. | The on-screen layout scripts are plain text whose grammar is not decoded, so where a value on screen comes from is not established here. |
| Menus & UI | `mvp05ps2.menus.widget_textures` | `offline-writer-proved` | Exports and re-imports the palettised widget art; the direct-colour team logos export. | A direct-colour import is refused, naming the missing encoder. Loading screens are listed only, and the nested dashboard screens are counted by the All Textures page rather than parsed. |
| All Textures | `mvp05ps2.textures.bank_inventory` | `read-only-mapped` | One table of every bank on the disc, each entry classified from its own header and each bank parsed for its directory. | No pixel is decoded; nothing is written to the disc, a save or the emulator. |
| Audio | `mvp05ps2.audio.streams` | `offline-writer-proved` | Lists every stream on the disc; plays and exports them; replaces the standalone stream files — the music beds, the crowd and heckle beds, the menu tracks — with a checked WAV. | The archived speech and the two commentary containers are refused by name: no decoder for their codec exists that this project could check against. An archived stream exports but is not replaced, and a replacement longer than the stream it replaces is refused. |
| Audio | `mvp05ps2.audio.banks` | `extract-only` | Exports the two sound banks. | No import — a bank sound is not replaced here, and the page states why in the row's own words. |
| Playbooks & Plays | `mvp05ps2.playbooks.tuning_tables` | `offline-writer-proved` | Baseball has no playbook, so this page carries the tuning that decides how the game plays: the progression and contract curves, the draft-class distributions, the schedules and the audio event tables, edited cell by cell. | The progression tables are stored with almost no slack, so an edit there must keep the table the same length or shorter and is refused by byte count otherwise. The one-line hex tables are not comma-separated and are not offered. |

## Pages that are deliberately empty

- **The Crib** — an ESPN NFL 2K5 feature and not an MVP Baseball concept, so
  the page stays empty here on purpose; Owner Mode's ballpark builder is art
  and is filed on the field-art page instead.
- **Gameplay** — no patch site on this disc's boot executable has been located
  by this project and no community patch for it is known here, so the page
  carries no lane rather than a scaffold with nothing on it.
- **Saves** — a memory-card save is not the disc, and this module works off the
  disc, so nothing here reads or writes a save.

## Limits

- The source image is opened for reading and is never modified; every Build
  writes a new image that must not already exist.
- Nothing is written to a memory-card save or to the emulator.
- Every edit is bounded by the slot it already occupies: no entry ever moves,
  and a replacement that no longer fits is refused, naming the size it had to
  meet.
- One compressed texture format on this disc has not been decoded. Every image
  that uses it — the high-detail jersey and trousers, the shoes, the faces, the
  field art, the crowd banks, the loading screens and the uniform preview
  swatches — is listed with its size and never drawn, exported or written.
- Direct-colour images export but never import: there is no encoder for them
  here.
- An imported PNG must be exactly the size of the image it replaces,
  palettised and non-interlaced. It is re-indexed against that image's own
  palette, so a colour the palette lacks takes the nearest entry, and the
  receipt says how many pixels landed exactly.
- Archived speech and commentary audio are refused by name. A replacement for a
  standalone stream is mixed to that stream's channel count and resampled to
  its rate, which the page states rather than doing quietly.
- Geometry has no reader, and the on-screen layout scripts are read as text
  only.
- The largest pages bound how many rows they offer as edit targets while the
  per-archive and per-table totals stay complete.
- No retail content lives in this repository — no cell value, string, pixel,
  sample or palette entry from any disc. CI proves the whole path on a
  synthetic disc built from the formats' rules.

## Evidence

For every capability above, the registry row is the claim. The module's tests
(`tests/mod_editor/test_mvp05_ps2_module.py`,
`tests/mod_editor/test_mvp05_ps2_lanes.py`) and the
`tools/validate_mvp05_ps2_*.sh` wrappers are the proof, and the independent
image verifier imports nothing that wrote the image: it re-derives every
declared byte with its own decoder, re-reads the archive out of both images,
compares every untouched entry byte for byte, and re-derives the edited content
from the recipe.

Every writer here is classified `offline-writer-proved` and no more. **No row on
this module is `runtime-proved`: no rebuilt image has been booted, and nothing
on this page has been confirmed in game.**

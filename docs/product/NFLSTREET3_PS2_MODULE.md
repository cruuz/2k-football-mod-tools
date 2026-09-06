# NFL Street 3 (USA, PlayStation 2) — module capability summary

This page is the capability summary for the `nflstreet3_ps2` game module: which
Studio pages it fills, what each one offers, what each one refuses, and how far
each claim has been proved. It is a reference for the shipped module, not a
study of the disc.

The user supplies their own legally obtained USA PlayStation 2 image of the
title. The tool bundles no game files, no BIOS, no saves and no emulator
binaries; every lane for this disc reads the user's own image and writes only
where the user asks.

The module sits on the game-module contract described in
`GAME_MODULE_CONTRACT.md`; `ADDING_A_GAME_MODULE.md` covers how a module of this
shape is assembled.

## Opening it

Start Mod Studio and choose **NFL Street 3 (PS2)** from *Select other games…*, or open it
straight from a terminal:

```
python -m mod_editor --game nflstreet3_ps2
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

The module works entirely off the disc image. It can:

- replace artwork — portraits, logos and cards, playfields, create-a-team field
  art, presentation screens and front-end menus — by supplying a PNG the same
  size as the texture it stands in for;
- edit the per-team player rows: the names, numbers and other values the page
  chooses to offer;
- edit team identity: team naming and the team's palette slots;
- edit the play library: rename a play, or move it;
- edit menu and interface strings in place;
- catalogue and export kit images and audio, without writing either back;
- list the disc's containers and their members read-only.

Every edit is applied by building a **new** disc image. The source image is
opened for reading and is never modified, and a build refuses a destination that
already exists.

## Studio pages

| Studio page | Registry row | Classification | What it does | What it will not do |
| --- | --- | --- | --- | --- |
| Names, Numbers & Faces | `nflstreet3ps2.players.team_databases` | `offline-writer-proved` | Pick a player in a team database, change a value, and Build writes a new image. | Offers only the fields the page can change safely and says so; a replacement string longer than its budget is refused by name with both lengths, and a number outside the field's measured bound is refused by the bound rather than silently truncated. |
| Text & Team Identity | `nflstreet3ps2.identity.team_records` | `offline-writer-proved` | Pick a team, change its names or its palette slots, and Build writes a new image. | Draws no colour swatch: the palette slots are references into a table this lane does not open, and the page says so. |
| Playbooks & Plays | `nflstreet3ps2.playbooks.play_databases` | `offline-writer-proved` | Pick a play, rename it or move it, and Build writes a new image. | Lists the fields it does not offer rather than exposing a control it cannot stand behind. |
| Menus & UI | `nflstreet3ps2.menus.text_members` | `offline-writer-proved` | Pick a string, type a replacement no longer than the slot, and Build writes a new image. | Cannot reach the fonts those strings are drawn with, and refuses a replacement that does not fit its slot. |
| Menus & UI | `nflstreet3ps2.menus.front_end_art` | `offline-writer-proved` | Replace a front-end texture with a PNG of exactly its size. | Refuses a PNG of any other size, or one that does not stay inside the colours the texture already carries. |
| Portraits & Faces | `nflstreet3ps2.rosters.portrait_art` | `offline-writer-proved` | Replace a portrait texture with a PNG of exactly its size. | Same size and colour rule; a replacement that would outgrow its slot on the disc is refused by name with both sizes. |
| Logos & Cards | `nflstreet3ps2.identity.logo_art` | `offline-writer-proved` | Replace a logo or card texture with a PNG of exactly its size. | Same size and colour rule. |
| Stadiums & Fields | `nflstreet3ps2.stadiums.playfield_art` | `offline-writer-proved` | Replace a playfield texture with a PNG of exactly its size. | Same size and colour rule. |
| Stadiums & Fields | `nflstreet3ps2.field_art.create_team_art` | `offline-writer-proved` | Replace a create-a-team field texture with a PNG of exactly its size. | Same size and colour rule. |
| Scorebug & Presentation | `nflstreet3ps2.presentation.screen_art` | `offline-writer-proved` | Replace a presentation screen texture with a PNG of exactly its size. | Same size and colour rule. |
| All Textures | `nflstreet3ps2.textures.container_inventory` | `read-only-mapped` | A table of every container on the disc and its members, with each member's format named. | Carries no control at all, and classifies only a sample of each container's members, saying how many it sampled. |
| All Textures | `nflstreet3ps2.textures.mmap_census` | `offline-writer-proved` | The catch-all art page: replace any remaining decodable surface with a PNG of exactly its size. | Same size and colour rule; surfaces this decoder does not read are not offered. |
| Uniforms & Equipment | `nflstreet3ps2.uniforms.texture_census` | `extract-only` | Catalogues the kit images and exports the ones this decoder reads as PNG. | Has no writer. All but three of the kit images are stored in a form nothing in this repository decodes; each is listed and refused by name. |
| Audio | `nflstreet3ps2.audio.streams` | `extract-only` | Catalogues the disc's streamed audio and exports what it can decode as WAV. | Has no import. Streams whose encoding this decoder does not read are refused by name. |
| Audio | `nflstreet3ps2.audio.banks` | `extract-only` | Catalogues the disc's sound banks and exports what it can decode as WAV. | Has no import. Sounds whose encoding this decoder does not read are refused by name. |

Long listings are bounded so a single very large archive cannot spend the whole
budget before the walk reaches the next container. Bounds apply to the rows
offered as targets; the totals the page reports stay complete.

## Pages that are deliberately empty

Three of the shell's pages carry no lane for this title, each for a stated
reason rather than by omission:

- **The Crib** — a concept from a different game and not an NFL Street feature,
  so the page stays empty here on purpose.
- **Gameplay** — no patch site has been located on this title's boot
  executable, and site research does not carry across titles; a patch writer
  with nothing behind it would be a control that could only refuse.
- **Saves** — this game keeps its progress on a memory card and there is no save
  artefact on the disc for the page to read; nothing has been captured from a
  memory card for this title in this project.

## Limits

- The source image stays read-only; a build produces a new image and refuses to
  overwrite an existing destination.
- Containers are rewritten inside the space the disc already gives them: a
  member that would grow past its slot is refused by name, with both sizes in
  the message, rather than written over its neighbour.
- Where the disc keeps preloaded copies of a container, every copy an edit
  disturbs is rewritten from the container's own new bytes, and a cached copy
  that would no longer fit is refused rather than written past the next one.
- Team palette slots stay read-only as colours: they are references into a
  table this module does not open, so no swatch is drawn for them.
- The kit page and both audio lanes are export-only — there is no writer behind
  any of them.
- Menu fonts, and the play and player fields the pages decline to list, stay
  read-only because the module cannot yet change them safely.
- The derived emulator replacement names shown on the art pages are computed,
  not confirmed by a dump; each art page states how many of its names are
  confirmed and how many are derived.
- A raw-CD style image is refused by name — the module reads the sector layout
  every PlayStation 2 DVD uses.
- Nothing retail is carried: the catalogue holds container names, member
  indexes, sizes, field names and counts, never a payload byte, a decoded pixel
  or a string from the game.

## Evidence

For each page above, the registry row is the claim: its classification is the
rung the module asserts and nothing here claims a rung above it. The proof is
the module's own tests and the `tools/validate_nflstreet3_ps2_*.sh` wrappers,
which run each lane's path end to end — including, for every writer, an
independent verifier that imports none of the writer and re-derives the result
from the two images alone, failing on any byte outside the declared ranges.

**Nothing in this module has been confirmed in game.** No row here is
classified `runtime-proved`: every writer is proved offline only, and no image
built by this module has been booted in an emulator or on hardware.

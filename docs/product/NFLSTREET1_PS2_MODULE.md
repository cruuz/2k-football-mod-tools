# NFL Street (USA, PlayStation 2) — module capability summary

This page is the capability summary for the `nflstreet1_ps2` game module: what the
module offers on each page of its Studio, what each page refuses, and where the
proof for those claims lives. It is a summary of shipped capability, not a study
of the disc, and it carries no format internals.

You supply the game. The module works only against a legally obtained USA
PlayStation 2 image of NFL Street (SLUS-20841); the tool bundles no game files,
no BIOS, no saves and no emulator binaries. Every lane for this disc reads your
own image and writes only where you ask it to.

## Opening it

Start Mod Studio and choose **NFL Street (PS2)** from *Select other games…*, or open it
straight from a terminal:

```
python -m mod_editor --game nflstreet1_ps2
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

Everything happens off the disc image. The module opens the disc's own archives
and offers edits to:

- the per-team player records — names, numbers, and the per-player values the
  page chooses to expose;
- the team records — team naming, the logo a team points at, and the colour
  slots it refers to;
- the play library;
- the on-screen text banks;
- the picture data behind portraits, team logos, create-a-team art, playfield
  art, presentation screens and menu art.

Two areas are readable but never written: the kit textures and the disc's audio.
Both export and accept nothing back.

A build never modifies the image you supply. It reads that image and writes a
new one, and it refuses a destination path that already exists.

## Studio pages

Classification words below are the registry's own and are used exactly as the
registry sets them; `GAME_MODULE_CONTRACT.md` defines what each rung means.

| Studio page | Registry row | Classification | What it does | What it will not do |
|---|---|---|---|---|
| All Textures | `nflstreet1ps2.textures.container_inventory` | `read-only-mapped` | Lists the disc's containers and the members inside them, naming the form each member holds. | Offers no control and writes nothing; listings are capped per container, so not every member appears as a row even though the reported totals stay complete. |
| All Textures | `nflstreet1ps2.textures.mmap_census` | `offline-writer-proved` | The catch-all picture row: pick any surface this decoder reads, supply a replacement image, and Build writes a new disc image. | Refuses a replacement that is not exactly the original's dimensions or that cannot be expressed with the member's own colours; refuses anything that would grow past the space the disc already gives it. |
| Portraits & Faces | `nflstreet1ps2.rosters.portrait_art` | `offline-writer-proved` | Replaces portrait art surface by surface, then Build writes a new disc image. | Same picture rules: exact dimensions, the member's own colours, no growth past its slot. |
| Logos & Cards | `nflstreet1ps2.identity.logo_art` | `offline-writer-proved` | Replaces logo and card art. | Same picture rules. |
| Stadiums & Fields | `nflstreet1ps2.field_art.create_team_art` | `offline-writer-proved` | Replaces the create-a-team art. | Same picture rules. |
| Stadiums & Fields | `nflstreet1ps2.stadiums.playfield_art` | `offline-writer-proved` | Replaces playfield art. | Same picture rules. |
| Scorebug & Presentation | `nflstreet1ps2.presentation.screen_art` | `offline-writer-proved` | Replaces presentation and screen art. | Same picture rules. |
| Menus & UI | `nflstreet1ps2.menus.front_end_art` | `offline-writer-proved` | Replaces front-end menu art. | Same picture rules. |
| Menus & UI | `nflstreet1ps2.menus.text_members` | `offline-writer-proved` | Pick a string, type a replacement, and Build writes a new disc image. | Refuses a replacement longer than the slot it goes into, naming both lengths; cannot reach the fonts those strings are drawn with. |
| Text & Team Identity | `nflstreet1ps2.identity.team_records` | `offline-writer-proved` | Pick a team and change its naming or the colour slots it refers to. | Draws no colour swatch — the slots are indices into a palette this lane does not open, and the page says so rather than showing a guess. |
| Playbooks & Plays | `nflstreet1ps2.playbooks.play_databases` | `offline-writer-proved` | Pick a play, rename it or move it, and Build writes a new disc image. | Lists values it does not offer as controls, and says which, rather than exposing an edit it cannot stand behind. |
| Names, Numbers & Faces | `nflstreet1ps2.players.team_databases` | `offline-writer-proved` | Pick a player, change a value, and Build writes a new disc image. | Refuses a replacement string longer than its budget and a number outside the measured bound for that value; neither is silently truncated. Values it does not understand are listed, not offered. |
| Uniforms & Equipment | `nflstreet1ps2.uniforms.texture_census` | `extract-only` | Catalogues the kit images and exports the ones this decoder reads as PNG. | Imports nothing. All but one kit image is stored in a form nothing in this project decodes; those are listed and refused by name, and no kit writer exists for that reason. |
| Audio | `nflstreet1ps2.audio.streams` | `extract-only` | Catalogues the disc's streams and exports the readable ones as WAV. | Imports nothing. Most streams are compressed speech that nothing here decodes, and each is refused by name. |
| Audio | `nflstreet1ps2.audio.banks` | `extract-only` | Catalogues the disc's sound banks and exports their readable sounds as WAV. | Imports nothing; unreadable sounds are refused by name rather than exported as noise. |

## Pages that are deliberately empty

Three of the Studio's pages carry no lane for this game. Each is empty on
purpose, and each says why on the page itself.

- **Crib** — a feature of a different football game entirely and not an NFL
  Street concept, so there is nothing here for the page to edit.
- **Gameplay** — no patch site has been located on this disc's boot executable,
  and patch sites are per-title research that does not carry over from another
  game's executable; the page carries no lane rather than a control that could
  only refuse.
- **Saves** — the game keeps its progress on a memory card and there is no save
  artefact on the disc to read, and nothing has been captured from a memory card
  for this title in this project. One exported save is what would lift the page.

## Limits

- Your image is opened for reading and never written; a build produces a new
  image and refuses a destination that already exists.
- Every container is rewritten inside the space the disc already records for it;
  anything that would grow past its slot is refused by name, with both sizes in
  the message, rather than written over its neighbour.
- Where an edit disturbs preloaded copies of the same data, every affected copy
  is rewritten from the same new bytes, and a cached member that has grown is
  refused rather than written past the next copy.
- Kit textures stay export-only, because all but one are stored in a form
  nothing in this project decodes.
- Audio stays export-only in both rows; nothing is written back into the disc's
  sounds.
- Colour slots are shown as numbers rather than swatches, because the palette
  they index is not opened by the lane that edits them.
- Fonts are out of reach: text can be replaced, but the shapes it is drawn with
  cannot.
- Some texture identities are confirmed against an emulator dump; the rest are
  derived by computation, and those derived emulator replacement names on this
  disc are unverified.
- A raw-CD style image is refused by name — the module needs the standard
  PlayStation 2 DVD sector layout.
- Listings are bounded so that one unusually large archive cannot crowd out the
  rest of the walk; the reported totals stay complete regardless.
- What the module ships is a structural catalogue — container and member
  identifiers, sizes, counts and digests. No payload bytes, no decoded pixels
  and no strings from the game are carried in this repository.

## Evidence

For each capability above, the registry row is the claim: it names the surface,
the classification, the GUI mode and the constraints the lane holds itself to.
The proof is the module's own tests
(`tests/mod_editor/test_nflstreet1_ps2_module.py`) together with the
`tools/validate_nflstreet1_ps2_*.sh` wrappers, which run each writer end to end
against a destination image and then re-derive the result with a verifier that
imports none of the writer and fails on any byte outside the declared ranges.

No row in this module is classified `runtime-proved`. Every writer here is
proved offline only: nothing on this page has been confirmed by booting the game
in an emulator or on hardware. `ADDING_A_GAME_MODULE.md` describes what a module
must show before a row may claim a higher rung.

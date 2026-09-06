# Madden NFL 09 (PlayStation 2) — module capability summary

This page is the capability summary for the Madden NFL 09 (USA, PlayStation 2)
game module: what its Studio pages offer, what each one refuses, and where the
line is drawn. It is a reference for someone deciding whether the module does
what they need — not a study of the disc and not a record of how anything was
worked out.

You supply the game. The module works from a legally obtained USA PlayStation 2
disc image, either the retail disc or the community's Madden NFL 09 Deluxe
rebuild, which it tells apart by the digest of the boot executable. It bundles
no game files, no BIOS, no saves and no emulator binaries; a disc that boots a
different serial is refused with a sentence saying so.

## Opening it

Start Mod Studio and choose **Madden NFL 09 (PS2)** from *Select other games…*, or open it
straight from a terminal:

```
python -m mod_editor --game madden09_ps2
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

Everything the module does is done offline, against your own image, and every
edit produces a **new** disc image beside it. The source is opened read-only and
never modified, the destination must not already exist, and the source may not
be named as the destination. Each lane offers a dry run that resolves every edit
before an image is built, shows its budgets and refusals inline, and finishes
with a receipt; an independent verifier then re-reads the destination with its
own decoder and gives the verdict.

In plain terms the module covers:

- Team and player data on the disc — names, jersey numbers, ages and ratings,
  team names, abbreviations and colours.
- Menu and UI text, one string slot at a time.
- The shipped playbooks' names, and a few numbers whose meaning is established.
- Disc art — uniforms and equipment, player and coach faces and portraits,
  field art, stadium art, and the in-game overlay textures.
- Audio — music and sound-effect streams play, export and can be replaced;
  bank sounds play and export.
- Four editor caps in the boot executable, delivered as an emulator patch file
  or written into a new image.
- A read-only inventory of every container on the disc.

## Studio pages

| Studio page | Registry row | Classification | What it does | What it will not do |
|---|---|---|---|---|
| All Textures | `madden09ps2.textures.container_inventory` | `read-only-mapped` | Lists every container on the disc with its members, their sizes and format labels, read straight off your image. | Offers no edit at all; very large containers are listed and left unread, and format labels come from a declared sample of each container rather than all of it. |
| Uniforms & Equipment | `madden09ps2.uniforms.mmap_export` | `extract-only` | Preview and export uniform and equipment textures as PNG, and check a candidate replacement for size and format before the writer row is used. | Does not write an emulator replacement pack — the file naming is worked out, but no pack built from it has been loaded. Textures in the second storage variant are refused by name rather than exported wrong. |
| Uniforms & Equipment | `madden09ps2.uniforms.disc_art_writer` | `offline-writer-proved` | Hand back an edited PNG at exactly the texture's own size and build a new disc image carrying it. | Will not accept a resized image, and cannot introduce a colour the texture's own colour table does not already hold. |
| Names, Numbers & Faces | `madden09ps2.players.team_databases` | `offline-writer-proved` | Edit a player's first and last name, jersey number, age and twenty ratings, or a team's nickname, city, abbreviation and short name. | Adds or removes nobody, and edits only the one container that no preload cache carries a second copy of; a rating stops at the game's own scale. |
| Names, Numbers & Faces | `madden09ps2.rosters.face_textures` | `offline-writer-proved` | Replace a player or coach face, a tattoo or a menu portrait with a same-size PNG and build a new image. | Does not touch a player's name, number, team or ratings — that is the row above. |
| Text & Team Identity | `madden09ps2.identity.team_records` | `offline-writer-proved` | Edit the four names each NFL team record carries, its two colours, and its city index, writing every copy of the record the disc's own databases agree on. | Leaves any copy that already disagrees alone and says which field made it differ; does not offer the four fields whose meaning is only a hypothesis. |
| Menus & UI | `madden09ps2.menus.text_members` | `offline-writer-proved` | Replace a menu or story string inside its own allocation, with that slot's budget on screen. | Refuses a replacement longer than the slot, refuses text carrying the byte that ends a string, and refuses to edit a container a preload cache carries a second copy of. |
| Playbooks & Plays | `madden09ps2.playbooks.databases` | `offline-writer-proved` | Rename formations, sets, set groups, plays and special-teams formations across the shipped playbooks, plus the handful of numbers whose meaning is established. | Adds and removes nothing — every shipped table is packed exactly full — and does not offer row ids, cross-references or undecoded numbers. |
| Stadiums | `madden09ps2.stadiums.textures` | `offline-writer-proved` | Preview, export and replace stadium textures at exactly their own size, then build a new image. | Leaves stadium geometry alone: the shape, the stands and the crowd have no decoder here. Members are unnamed on the disc, so which stadium a texture belongs to is not established. |
| Field Art & Create-Team Art | `madden09ps2.field_art.textures` | `offline-writer-proved` | Preview, export and replace the field textures, then build a new image. | Leaves the geometry in the same container alone, and offers no create-team art — none has been located on this disc. |
| Presentation | `madden09ps2.presentation.ui_textures` | `offline-writer-proved` | Preview, export and replace the in-game overlay textures the executable draws with. | Does not change the scorebug's layout or its numbers, which the executable draws; the overlay fonts wait on a decoder, and some UI containers hold nothing this lane can offer. |
| Audio | `madden09ps2.audio.streams` | `offline-writer-proved` | Play and export music and sound-effect streams, and import a checked WAV back into a new image. | Refuses speech and commentary by name — nothing here or in ffmpeg decodes that codec — and refuses a replacement longer than the sound it replaces, naming the size it had to fit. |
| Audio | `madden09ps2.audio.banks` | `extract-only` | Play and export bank sounds from your own image. | Has no writer at all; every value offered for a bank sound is refused. |
| Gameplay | `madden09ps2.gameplay.executable_patches` | `offline-writer-proved` | Raise four editor caps — formations, sets, plays per book and plays per set — delivered as an emulator patch file beside the image or written into a new one. | Will not lower a cap below what the executable already enforces, will not exceed what the check can carry, and offers nothing for the other tuning subjects, whose controls are drawn read-only because no site has been located for them. |

## Pages that are deliberately empty

- **The Crib** — an ESPN NFL 2K5 feature and not a Madden concept, so the page
  stays empty here on purpose.
- **Saves** — a memory-card save is another repository's tooling; this studio
  works off the disc and neither reads nor writes a save.

## Limits

- **Nothing has been confirmed in game.** No row in this module is classified
  `runtime-proved`: no rebuilt Madden 09 image has been booted in an emulator
  or on hardware, so nothing here claims the game loads or draws the result.
- **Geometry stays read-only** — stadium and field shapes, stands and crowds
  have no decoder anywhere in this repository, so they are listed and left
  alone.
- **Speech and commentary stay read-only** — the great majority of the disc's
  streams use a codec nothing here decodes, so they are listed with their rate,
  channels and length and their audio is refused rather than guessed at.
- **Overlay fonts stay read-only** — they wait on a decoder that does not exist
  here yet.
- **Nothing grows** — a replacement must fit the space the original occupied,
  and no lane adds a player, a play or a table row.
- **Colour is bounded by the original** — a replacement texture is matched
  against the colour table the texture already carries, so a colour that table
  does not hold cannot be introduced.
- **Containers a preload cache copies are refused** — where the disc keeps a
  second copy of something, editing one copy and not the other is refused by
  name rather than written half-done; the list is read off your own image.
- **The module is retail-free** — it carries names, sizes, counts and digests
  only. No pixel, sample, string or member payload from the game lives in this
  repository, and the whole path is exercised in CI against synthetic discs
  built from the format's own rules.

## Evidence

The registry row is the claim: its classification, its stated reason and its
constraints are what the module promises, and no page here claims a rung above
the one the registry records. The proof is the module's own tests together with
the `tools/validate_madden09_ps2_*.sh` wrappers, which run each lane end to end
against your image and hand the result to a verifier that imports none of the
code that wrote it.

That proof stops at the file. Every writer above is `offline-writer-proved` and
nothing more: the edit reads back out of the destination, untouched bytes are
untouched, and the image parses as a disc in its own right — but no rebuilt
image has been run, so nothing here is a statement about what Madden NFL 09
does with it.

For what a classification means and what a module must satisfy to carry one,
see `GAME_MODULE_CONTRACT.md`; for adding another game on the same contract,
see `ADDING_A_GAME_MODULE.md`.

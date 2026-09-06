# NCAA Football 09 (PlayStation 2) — module capability summary

This page is a capability summary for the NCAA Football 09 (PlayStation 2) game
module: which Studio pages carry a working lane, what each one does, at what
level of proof, and where it stops. It is not a study of the disc.

The user supplies their own legally obtained USA PlayStation 2 disc image
(SLUS-21752). The tool bundles no game files, no BIOS, no saves and no emulator
binaries. Every lane opens the user's image for reading; a build writes a new
image beside it and never modifies the source.

## Opening it

Start Mod Studio and choose **NCAA Football 09 (PS2)** from *Select other games…*, or open it
straight from a terminal:

```
python -m mod_editor --game ncaa09_ps2
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

Editing on this disc falls into three groups.

- **Text and identity.** The names carried for schools, conferences, divisions,
  stadiums and coaches, and the string slots behind the menus and UI.
- **Rosters and playbooks.** Per-player squad number, position, class, redshirt
  flag, height, weight and attributes, together with the depth-chart entries
  beside them; and the name of every named row in every playbook.
- **Two-dimensional art.** Uniform and equipment textures, player and coach
  faces, field art, stadium art and presentation art. A texture is edited by
  exporting it, painting the PNG, and giving back an image of exactly the same
  size.

Three further pages read and never edit: a whole-disc texture inventory, an
inspector for a draft-class memory-card save, and an audio catalogue that
exports to WAV.

Every write on this disc is a *fixed-allocation* write. A replacement occupies
the space the original occupied; one that would need more room is refused by
name, with the amount it is over, before any image is produced. A dry run
resolves every edit first, and an independent verifier that shares no code with
the writer gives the verdict by re-reading the finished image.

## Pages and rows

| Studio page | Registry row | Class | What it does | What it will not do |
|---|---|---|---|---|
| Names, Numbers & Faces | `ncaa09ps2.players.league_databases` | `offline-writer-proved` | Edits a player's squad number, position, class, redshirt flag, height, weight and attributes, plus the depth-chart fields beside them, across every per-team roster. | Draws no name field — this disc's players have none — and no 0–99 rating spinner; adds and removes no row, and renumbers no player. |
| Names, Numbers & Faces | `ncaa09ps2.rosters.face_textures` | `offline-writer-proved` | Replaces a player or coach face texture from a PNG of exactly its size. | Cannot say which player or coach a face belongs to; no join exists on this disc. |
| Text & Team Identity | `ncaa09ps2.identity.league_records` | `offline-writer-proved` | Edits the names carried for each school, conference, division, stadium and coach, with each field's own budget on screen. | Draws no colour control: there is no team colour field to write into, and which palette entry a school uses is not established. |
| Menus & UI | `ncaa09ps2.menus.text_members` | `offline-writer-proved` | Edits menu and UI string slots, with the room each has on screen and a preview read from the user's own image. | Refuses a bank that the disc's preload caches also copy, and cannot say which characters have a glyph in the shipped fonts. |
| Playbooks & Plays | `ncaa09ps2.playbooks.databases` | `offline-writer-proved` | Renames any named row of any playbook. | Offers no other column — their meaning is not established — and adds no play: the tables ship packed full. |
| Uniforms & Equipment | `ncaa09ps2.uniforms.disc_art_writer` | `offline-writer-proved` | Replaces a uniform or equipment texture from a PNG of exactly its size. | Edits no kit record — the create-a-school tables ship empty — and cannot say which school a texture belongs to. |
| Uniforms & Equipment | `ncaa09ps2.uniforms.texture_census` | `extract-only` | Previews and exports uniform and equipment textures to PNG, with each texture's replacement identity marked confirmed or derived. | Writes nothing back; refuses a destination that is the source, and refuses by name any entry its decoder will not draw. |
| Stadiums | `ncaa09ps2.stadiums.textures` | `offline-writer-proved` | Replaces a stadium texture from a PNG of exactly its size. | Leaves the geometry in the same containers alone — no decoder here — and edits no stadium name, city or capacity. |
| Field Art & Create-Team Art | `ncaa09ps2.field_art.textures` | `offline-writer-proved` | Replaces a field or create-team art texture from a PNG of exactly its size. | Creates no team: the create-a-school colour and uniform tables ship empty, and no container names which field or school a texture is. |
| Presentation | `ncaa09ps2.presentation.ui_textures` | `offline-writer-proved` | Replaces a presentation texture from a PNG of exactly its size. | Does not lay out the scorebug — that is drawn by the executable — and leaves the models and movie streams alone. |
| All Textures | `ncaa09ps2.textures.container_inventory` | `read-only-mapped` | Lists every container and member on the image with its format and codec, read straight off the user's disc. | Offers no edit; there is no container writer behind this page, and outsized containers are listed by size and left unread. |
| Saves | `ncaa09ps2.saves.draft_class` | `read-only-mapped` | Inspects a draft-class memory-card save, one row per non-empty pick, and reports how many slots are empty. | Writes nothing: a compiler for this exact file already exists outside this repository. |
| Audio | `ncaa09ps2.audio.banks` | `extract-only` | Catalogues bank sounds and exports them to WAV. | Replaces no sound; refuses any entry that declares no length or no sample rate. |
| Audio | `ncaa09ps2.audio.streams` | `extract-only` | Catalogues streams and exports the decodable ones to WAV. | Replaces no stream, and refuses by name any stream in a codec this module does not decode — most of them. |

## Pages that are deliberately empty

- **The Crib** — an ESPN NFL 2K5 feature and not an NCAA Football concept, so
  the page stays empty here on purpose.
- **Gameplay** — no patch site has been located on this disc's boot executable,
  and every site is per-title research that does not carry over from another
  game; the page carries no lane rather than a control that could only refuse.

## Limits

- Team colours stay read-only: there is no colour field on this disc to write
  into, and which palette entry a school uses is an open question.
- Team creation stays unavailable: the create-a-school colour, kit and uniform
  tables ship with no rows at all.
- Player names stay absent: this disc carries none, so no page offers one.
- Attribute values use the disc's own narrow scale, not the familiar 0–99 one,
  and what the game draws from that scale is not established here.
- No row is added or removed anywhere: the databases ship packed, so an
  insertion has nowhere to go and is refused rather than attempted.
- One string bank stays read-only because the disc's preload caches also copy
  it, and editing one copy would leave the game reading whichever it reached
  first.
- Audio stays export-only: there is no writer, and most streams are in a codec
  this module does not decode.
- The whole-disc texture inventory lists and never edits, and leaves the
  largest containers unread so they never enter memory.
- Geometry, models and movie streams are left alone: no decoder for them exists
  here.
- The scorebug is drawn by the executable, so no art page can lay it out.
- Draft-class saves are inspected only: a second implementation of a format
  that already has one is how two of them start to disagree.
- No page relocates anything. A rewrite that would need more room than the
  original occupied is refused by name rather than moved.

## Evidence

The registry row is the claim. The module's tests and the
`tools/validate_ncaa09_ps2_*.sh` wrappers are the proof: the writers are
exercised end to end against a user-supplied image, and each is checked by a
verifier that imports none of the writer, re-reads the finished image, and fails
on any byte changed outside the declared ranges.

**No row in this module is classified `runtime-proved`.** Nothing described on
this page has been confirmed by booting NCAA Football 09; no rebuilt container
and no exported texture pack has been loaded in an emulator. Every row here
stands on offline evidence alone, and the classification on each row says
exactly how far that evidence reaches.

The contract these rows are written against is described in
`docs/product/GAME_MODULE_CONTRACT.md`; `docs/product/ADDING_A_GAME_MODULE.md`
covers bringing another game onto it.

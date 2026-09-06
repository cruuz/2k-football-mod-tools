# ESPN NFL 2K5 (PlayStation 2) — module capability summary

This page summarises what the ESPN NFL 2K5 PlayStation 2 module can do, page by page: what
each lane edits, what it refuses, and how strong the claim behind it is. It is a capability
summary and not a study — it describes the shipped behaviour, not how any of it was worked
out. To use the module the user supplies a legally obtained USA PlayStation 2 disc image
(serial SLUS-20919) whose digest matches the supported retail release; the tool bundles no
game files, no BIOS, no saves and no emulator binaries. This repository also carries a
module for the Xbox release of the same game — nothing on this page describes it.

## Opening it

Start Mod Studio and choose **ESPN NFL 2K5 (PlayStation 2)** from *Select other games…*, or open it
straight from a terminal:

```
python -m mod_editor --game nfl2k5_ps2
```

Point it at your own disc image. The module checks that the image is the release it
supports and refuses by name if it is not, so a wrong disc costs you a sentence rather
than a bad build.

## Before you build anything

**All but one writer in this module is proved offline and has never been seen in a
running game.** Precisely: the rebuilt image is checked byte for byte by a verifier that shares
no code with the writer, each edit is confirmed to land inside the range its capability
row declares, and every other byte of the image is confirmed unchanged. What that does
not cover is the game itself — nobody has booted the result. If you load a rebuilt image
in an emulator or on hardware you are the first person to do so, and a crash, a missing
texture or a wrong string is a real possibility rather than a surprise. Please report
what you see.

The one exception is the exact-slot audio replacement
(`nfl2k5ps2.audio.audo_exact_slot_replace`), which has been heard in a running game and is
the only `runtime-proved` row in this repository's PlayStation 2 modules.

A build always writes a **new** image, to a destination that does not already exist. The
disc image you supply is opened for reading and is never modified, so a bad build costs
you the output file and nothing else.

## What the module edits

Every editing lane works on a copy of the user's own image and never on the image itself,
and every one of them runs the same three steps. A catalogue tool reads the user's disc and
produces the list of targets that lane will accept. The patcher plans the edit and shows its
refusals before any output exists. The build then writes a new image, and an independent
verifier — code that does not import the patcher — gives the verdict. The source is opened
read-only and re-hashed afterwards; the destination is created exclusively, so a run can
neither overwrite an existing image nor land on the one it read; and a refusal leaves no
output behind.

In plain terms the module edits menu and franchise text, on-disc roster names and jersey
numbers, uniform colours, playbooks and the plays inside them, stadium position lanes, and
individual sound slots. Two further lanes never write to a disc at all: a read-only
inventory of what is on it, and an export that turns the user's own uniform edits into an
emulator texture-replacement pack. Memory-card saves are handled by their own window rather
than by a disc lane, because a save is not the disc.

## Studio pages

| Studio page | Registry row | Classification | What it does | What it will not do |
|---|---|---|---|---|
| Audio | `nfl2k5ps2.audio.audo_exact_slot_replace` | `runtime-proved` | Replaces one catalogued sound slot with a user-supplied uncompressed WAV, matched to the slot's own channel count and sample rate. | Never lengthens a slot or borrows room from a neighbour; refuses an over-long clip with the slot's exact capacity in seconds rather than truncating it; accepts a catalogue slot id, or a name only where that name is unique on the disc, never a raw offset or a guessed filename. |
| Menus & UI | `nfl2k5ps2.menus.text_banks` | `offline-writer-proved` | Rewrites display copy in the franchise, credits, situation and trivia banks, shorter or equal to the original. | Refuses one character over budget; will not touch the in-game HUD or play-call text, which lives in none of the disc's text banks; leaves lookup selectors and zero-capacity entries read-only; refuses a compressed bank and a bank spanning two pack files. |
| Text & Team Identity | `nfl2k5ps2.colors.unif_words` | `offline-writer-proved` | Sets the colour words on a catalogued uniform selector, with home, away, alternate and throwback treated as independent records. | Accepts only catalogued selectors and only exact-size colour literals; refuses a compressed body rather than re-encoding it; refuses a no-op, and refuses a recipe authored against a different image. |
| Names, Numbers & Faces | `nfl2k5ps2.players.disc_roster` | `offline-writer-proved` | Renames a player in the disc's seed rosters, shorter or equal, and sets a jersey number within range; a historic roster is written from its own data, never another's. | Will not grow, move or reallocate anything; team membership, ratings, position and face selection are not writes; the many bare placeholder name slots have no room and are refused, as are a shared name string, a compressed body and a no-op. |
| Playbooks & Plays | `nfl2k5ps2.scripts.director_playbook` | `offline-writer-proved` | Edits plays and formations in a book and creates new ones in slots proved empty, within the book's own capacities, with every created play put through the ported retail validator before it is staged. | Never grows or relocates a book or its pack; refuses adding a play to a book already at its cap, and says what the count would need to be; will not re-encode a compressed family; the risk that a memory-card play overlays a disc book at load is untested and is stated in the interface. |
| Stadiums | `nfl2k5ps2.stadiums.position_lanes` | `offline-writer-proved` | Moves catalogued position lanes in a stadium scene, keeping the same number of points. | Positions only — changing the count would be a topology change and is refused; every other byte of the scene is preserved as the user's; refuses two edits that alias one lane, a recompression that will not fit, and a recipe spanning two scenes. Off by default, because a catalogue and a build take tens of minutes and only one scene is proved. |
| PS2 Disc Inventory | `nfl2k5ps2.textures.disc_inventory` | `read-only-mapped` | Walks the user's disc and lists what is on it — names, formats, dimensions and Xbox counterparts — and exports that listing. | Never modifies the image; reads only the descriptive half of each resource and never the pixels or samples, so no output can carry retail payload; offers no edit anywhere, because there is no PlayStation 2 texture writer. |
| Uniforms and PCSX2 Pack | `nfl2k5ps2.uniforms.replacement_pack_export` | `extract-only` | Publishes the uniform textures the user actually edited as an emulator replacement pack, named from the shipped manifest, into a fresh folder with a receipt, and asks where the pack will be used before writing anything. | Never writes an unedited texture, because that would be retail pixels leaving the disc; never reads or writes an ISO on this path; skips a target with no manifest name, or an ambiguous one, and says so; will not publish into a folder that already exists. |
| Memory-card saves (own window) | `nfl2k5ps2.saves.roster_name_writer` | `offline-writer-proved` | An upstream row, listed here for completeness: a fixed-allocation roster-name writer for a memory-card save, paired with its own verifier, refusing any name longer than the one it replaces. | — |
| Gameplay tuning | `nfl2k5ps2.gameplay.executable_patches` | `unknown` | Maps and refuses; see below. | Writes nothing. |

Exactly one row is classified `runtime-proved`: the audio slot writer, and it is the only
one in the module. Its bytes are proved and one replaced slot was heard on a cold boot;
every other slot's in-game cue is unproved, and because a name can be shared by more than
one slot the interface warns that a replacement may change an unexpected cue. Every other
row is `offline-writer-proved`, `read-only-mapped` or `extract-only` — proved offline and on
synthetic sources, not confirmed in game.

Exactly one row is classified `unknown`: the gameplay-tuning lane. Its interface, its patch
emitter and its independent verifier exist and are proved on a synthetic executable, but no
host patch has a located site in this game's PlayStation 2 executable and no Xbox address
transfers to it. **The lane therefore maps and refuses rather than writes**: every
translation is declined with its reason, and nothing it does changes a disc or an emulator.
An `unknown` row stays hidden in the interface, so no window lists a patch. Delivery, when
there is something to deliver, is an emulator patch file applied at load time, with on-disc
patching as a later and optional second route; the row moves off `unknown` one patch at a
time, as translations are proved.

## Pages that are deliberately empty

- **Field art** — field and create-team art live in the same texture packs as the uniforms,
  so the page arrives with the uniform art lane rather than before it.
- **Presentation** — the scorebug and the broadcast overlays are drawn by the executable
  rather than by a data file this toolchain can find; nothing on this disc has been mapped
  to them.
- **Crib** — the Crib assets have not been located on the PlayStation 2 disc yet.

Memory-card saves are absent from the lane list for a different reason: a save is not the
disc, so it is a separate window (the PS2 Save Editor, on the Windows menu) rather than a
lane.

## Limits

- **Fixed allocation everywhere.** No editing lane grows, moves or reallocates anything; an
  over-long input is refused with its budget stated, never truncated to fit.
- **Compressed bodies are refused rather than re-encoded**, on every lane whose retail data
  is not compressed — shipping an unexercised path would claim more than the evidence
  supports, and the refusal is still exercised against a synthetic source.
- **Player identity beyond names and numbers stays read-only.** Team membership, ratings,
  position and face selection are not writes on any lane.
- **In-game HUD and play-call text cannot be changed**; it is in none of the disc's text
  banks, so the menus lane does not claim it.
- **There is no PlayStation 2 texture writer.** Textures can be inspected and exported for
  an emulator to load; they are never written back into a disc image.
- **Stadium edits are positions only**, on one proved scene, and the lane is off by default
  because a run takes tens of minutes.
- **A loaded roster or franchise save may override the disc seed**, so a disc-side roster
  edit is not guaranteed to be what a given user sees.
- **Gameplay tuning writes nothing today** and is hidden until a translation is proved.

## Evidence

The claim for each capability is its row in the shipped capability registry: the row carries
the classification, the reason it is exposed the way it is, and the full set of constraints
the lane enforces. This page summarises those rows; where the two ever disagree, the
registry is right.

The proof is the module's own tests together with the shipped validator wrappers that run
beside them — `tools/validate_nfl2k5_ps2_*.sh`, and the matching `.bat` for Windows, roughly
one per lane. Each lane ships a synthetic source, so the whole set runs from a shipped tree
with no game data present and nothing but the tool's own fixtures. For what a game module is
required to provide, and how another one is added, see `docs/product/GAME_MODULE_CONTRACT.md`
and `docs/product/ADDING_A_GAME_MODULE.md`.

# Disc mapping runbook — one disc, one command, one page

This is the procedure for turning a PlayStation 2 disc the owner holds into a **disc map**: a
retail-free page under `docs/product/disc_maps/` that says what is on the disc, in what
containers and formats, and therefore which studio pages a game module could fill and at which
registry rung. It is written so that a low-reasoning agent, or a person in a hurry, can do it
without judgement calls. Where a step needs judgement, the runbook says so and stops.

## Rules (read before anything else)

1. **Read-only.** The image is never modified, copied, renamed or moved. The mapper opens it
   read-only. Nothing is extracted from it except into memory.
2. **Retail-free outputs.** Only counts, names, sizes, offsets, digests and format ids leave the
   disc. Never quote game text, never save a decoded texture, never paste a hexdump of a member
   into a repository file. The mapper already obeys this; the page you write must too.
3. **No emulator.** Mapping never launches PCSX2 or PenguinScreen2 and never touches
   `wivrn-server`. If a step seems to need the game running, it is not a mapping step.
4. **The rig is where the discs live.** Run the mapper there over SSH; bring back only the
   `.map.json` and `.map.md` files.
5. **One disc, one page.** The page follows `docs/product/disc_maps/TEMPLATE.md` exactly. Every
   sentence in it comes from the map or from a cited document; mark anything else `[A]`.
6. **Do not commit.** Write the page into the scratch area named by whoever dispatched you; the
   integrator commits with the owner's identity.

## The tool

`tools/ea_disc_map.py` (shipped, selftested, stdlib + this repository only):

    PYTHONPATH=. python3 tools/ea_disc_map.py --iso "<image>.iso" --out <dir> --label "<Title> (USA)" --hash-image
    PYTHONPATH=. python3 tools/ea_disc_map.py --render <dir>/<SERIAL>.map.json    # Markdown again from the JSON
    PYTHONPATH=. python3 tools/ea_disc_map.py --selftest

It writes `<SERIAL>.<label-slug>.map.json` (everything) and `<SERIAL>.<label-slug>.map.md` (the summary); the label is in the
name because a Deluxe disc shares its serial with the retail one. It maps: identity
(boot file, serial, boot-ELF sha256 and PCSX2 CRC, whole-image sha256), every file's kind from its
magic, every `TERF` container's chunk chain, alignment, codec and decompressed-format histograms,
MMAP texture dimensions, TEXT totals, nested containers, and the EA TDB schema of every database
member (each distinct table/field shape once), EA `BIGF` archives (entries, member kinds, `SHPS` texture
members), plus bare databases. Containers are read through a memory map, so a 1.7 GB movie container
costs no memory. A refusal is a sentence in the table, never a traceback. Madden 09 maps in about 30 s;
Madden 2004 with its 1.7 GB movie container in about 40 s.

## Steps

1. Confirm the disc exists on the rig, read-only:
   `ssh pacarey@192.168.68.85 'ls -la ~/Games/ps2/ | grep -i "<title>"'`
2. Run the mapper on the rig (the clone lives at `~/2k-football-mod-tools-ps2`, kept at the lane's head):
   `ssh pacarey@192.168.68.85 'cd ~/2k-football-mod-tools-ps2 && PYTHONPATH=. python3 tools/ea_disc_map.py --iso ~/Games/ps2/"<image>.iso" --out ~/ps2-maps/out --label "<Title> (USA)" --hash-image --quiet'`
   Expected: one line `EA_DISC_MAP_DONE serial=<SERIAL> files=… containers=… databases=… schemas=… seconds=…`.
   A disc with `containers=0` is not an EA TERF disc: read its *File kinds* and *Archives* tables instead (VC packs for
   ESPN titles; `BIGF` archives + `SHPS` textures for MVP Baseball).
   Anything else: stop and report the line verbatim.
3. Fetch the two files: `scp pacarey@192.168.68.85:~/ps2-maps/out/<SERIAL>.<label-slug>.map.* <your scratch dir>/`
4. Open `<SERIAL>.map.md`. Fill `docs/product/disc_maps/TEMPLATE.md` into `<your scratch dir>/<SERIAL>.md`:
   every table cell from the map, the page-by-page rung table from the rules below, nothing else.
5. Self-check before reporting: no game strings quoted; every number traceable to the map; the
   identity row matches the mapper's line; the rung table uses only the five rungs named below.

## Rung rules (mechanical)

For each studio page, look at the containers whose decompressed formats feed it:

| page | feeding formats | day-one rung when the format is… |
|---|---|---|
| Uniforms & Equipment, Field Art, Stadiums (textures), All Textures | `MMAP` | read-only-mapped (inventory) → extract-only once a PNG decoder exists for that title |
| Names, Numbers & Faces; Text & Team Identity (team data) | `TDB` members, bare `.DB` files | read-only-mapped (schema + rows) → offline-writer-proved only when an independent verifier exists |
| Text & Team Identity, Menus & UI | `TEXT` members | read-only-mapped → extract-only |
| Audio | `SCHl` | extract-only (decode to WAV) only if a decoder exists; otherwise read-only-mapped; never a writer (no public encoder) |
| Stadiums (geometry) | `SMF` | read-only-mapped |
| Playbooks & Plays, Gameplay | executable / data | `unknown` until a lane exists; the code-patch scaffold is `unknown` |
| The Crib, Saves | not on the disc | honest empty page |

A container that is `COMP` with LZH1 members can be read but **not rewritten** until an LZH1 encoder
exists; note "read-only until the LZH1 encoder" on every writer row it would block. A `DATA`
container, or a `COMP` container whose relevant members are stored (codec 0), can be rewritten with
`ea_terf.rewrite_member` / stored members.

## What the integrator does with the page

Reviews it against the map, commits it as `docs/product/disc_maps/<SERIAL>.md` with the owner's
identity, and files the module work it implies in `GAME_STUDIO_SHELL_PLAN.md`.

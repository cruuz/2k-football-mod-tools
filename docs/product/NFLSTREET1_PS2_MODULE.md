# NFL Street (USA, PlayStation 2) — the module

`SLUS-20841`. The seventh game on the Game Studio shell, and the first built
entirely out of shared lane bases: there is no lane *shape* in this package, only
which containers this disc has and what its schema says. Read
`docs/product/MODULE_AGENT_CHARTER.md` first; this page is the one module
document for this game.

**Evidence tags.** **[M]** measured on the retail disc this project holds; **[S]**
sourced from a named document; **[A]** assumed.

---

## 1. What the disc is

| | |
|---|---|
| Serial | `SLUS-20841` |
| Boot file | `SLUS_208.41`, 3,257,248 bytes |
| Boot ELF sha256 | `1b5ceccd4e6bb7005320a93a24ee7614b7f5c03540ca9fc0a435b09c1da7728b` [M] |
| Image sha256 | `cb197dbdd468f05c3099147aa802e8f4f315d1bb3a21e62b4a17fd34e6205613` [M] |
| Image | 2,077,655,040 bytes, 131 files, 6 directories, 2048-byte sectors [M] |
| PCSX2 CRC | `03C2C5B1` [M] |

It is an EA Tiburon disc of the same container family as Madden NFL 09 and NCAA
Football 09, four years earlier. Every shared reader opens it with nothing
changed [M]:

| | |
|---|---|
| `TERF` containers | **48 of 48** open |
| Members | **8,803 of 8,803** |
| EA `TDB` databases | **38 of 38** (32 in `DB_TEAMS.DAT`, 4 in `TEMPLATE.DAT`, 2 in `IGDATA.DAT`) |
| CRC-32/MPEG-2 slots | **570 of 570** already hold the value they recompute to |
| `MMAP` members | 2,785 |
| `TEXT` string banks | 531 |
| `SCHl` streams | 679 · `BNKl` banks 236, holding 1,031 sounds |
| `QL01` preload caches | **9** — `FE.QKL` and `GAME0.QKL`..`GAME7.QKL` |
| Preload copies | **1,693 copies of 37 containers, every one byte-identical to what it copies** |

`docs/owner/scoping/readiness/SLUS-20841.NFL-Street-USA.readiness.json` is the
census this table quotes.

---

## 2. The schema, and how it differs from NFL Street 3

Two games three years apart. **The container formats are identical and no record
schema is**, with exactly one exception. Measured by walking every TDB in
`DB_TEAMS.DAT` and `IGDATA.DAT` on both discs; the full field-by-field census is
`docs/product/measured/nflstreet1_ps2/tdb-schema-difference.json` [M].

| table | NFL Street | NFL Street 3 | common names | same width | **same width *and* offset** |
|---|---|---|---|---|---|
| `PLAY` | 65 fields / 671 bits / 84 B | 84 / 831 / 104 | 64 | 49 | **0** |
| `TEAM` | 41 / 575 / 72 | 22 / 447 / 56 | 21 | 20 | **0** |
| `DCHT` | 4 / 63 / 8 | 4 / 63 / 8 | 4 | 4 | **4** |
| `PBST` | 27 / 511 / 64 | 5 / 127 / 16 | 5 | 3 | 0 |
| `PBPL` | 4 / 63 / 8 | 5 / 255 / 32 | 4 | 1 | 0 |
| `PLYL` | 10 / 319 / 40 | 10 / 255 / 32 | 10 | 2 | 0 |
| `SETL` | 8 / 287 / 36 | 8 / 191 / 24 | 8 | 2 | 0 |
| `FORM` | 3 / 223 / 28 | 3 / 95 / 12 | 3 | 1 | 0 |
| `PBFM` | 5 / 479 / 60 | 9 / 191 / 24 | 5 | 1 | 0 |

**`DCHT` is the only table that ports byte for byte** — same four fields,
`PGID`/`TGID`/`PPOS`/`ddep` at 15/10/5/5 bits, at the same offsets. Everything
else has to be read from the file's own field directory, which is what the
metadata-driven bases do.

What each disc has that the other does not:

* **Street 3 adds 20 `PLAY` fields** and drops one (`PAWR`). The twenty are
  almost all a create-a-baller face block — `PFEA`, `PFEB`, `PFEY`, `PFFH`,
  `PFHC`, `PFJC`, `PFLP`, `PFMO`, `PFNO`, `PFBW`, `PHDC`, `PJCT`, `PHTM`,
  `PSTM`, `PMED`, `PBTO`, `PLIL`, `PLPR`, `PJUM`, `TGTI` — and **every one of
  them is 0 on all 449 of that disc's rows** [M]. Fifteen more fields widened,
  including `PFNA` 88→96 bits, `PLNA` 104→112 and `PNKN` 104→128.
* **NFL Street's `TEAM` carries 20 fields Street 3 dropped**: `LGID`, `SGID`,
  `TMSA`, `TLSA`, `TLGS`, `TGPT`, `TGRP`, `TDPB`, `TOPB`, `TRDB`, `TRQB`,
  `TRRB`, `TROL`, `TRDL`, `TRLB`, `TRST`, `TFTL`, `TWRR`, `TVQS`, `TAss` —
  eleven of them per-position team ratings. Street 3 keeps three (`TROF`,
  `TRDE`, `TROV`) and adds one, `CTDL`.
* **NFL Street's `PBST` carries the route grid**: 22 of its 27 fields are
  `ax0_`..`ax10` (16-bit) and `ay0_`..`ay10` (8-bit), eleven route points.
  Street 3 removed the whole block and added `PBFM.FAU1..FAU4` and a `name` on
  `PBPL` instead.

**The rating scale is 0..100, not Madden's 0..99.** Read off all 402 `PLAY` rows:
`PAGI`, `PAWR`, `PBLK`, `PBTK`, `PCOV`, `PCTH`, `PSPD` and `PPSS` all reach
**100**; the fields are 7 bits and would hold 127 [M]. `POVR` tops out at 99.
`PAGE` is **0 on every row** — a street baller has no listed age — and `PRFC` is
63, its own ceiling, on every row; neither is offered.
`docs/product/measured/nflstreet1_ps2/db-teams-value-ranges.json` is the census.

---

## 3. The fourteen pages

| page | lane | rung | what it reaches |
|---|---|---|---|
| Uniforms & Equipment | `uniforms.texture_census` | extract-only | `PLATEX.DAT`, 1,735 members; **1 decodes** — see §4 |
| Names, Numbers & Faces | `players.team_databases` · `rosters.portrait_art` | offline-writer-proved ×2 | 402 player rows · 549 portraits |
| Text & Team Identity | `identity.team_records` · `identity.logo_art` | offline-writer-proved ×2 | 32 `TEAM` rows · 102 logos |
| Field Art & Create-Team Art | `field_art.create_team_art` | offline-writer-proved | 97 surfaces (`UIS_CRTM`, `UIS_FSEL`) |
| Stadiums | `stadiums.playfield_art` | offline-writer-proved | 34 surfaces (`ENVRNMT`, `OBJMODEL`, `STATMOD`) |
| Presentation | `presentation.screen_art` | offline-writer-proved | 155 surfaces (`LOADDATA`, `UIS_INGM`, `UIS_MOVI`, `UIS_ONRE`) |
| Menus & UI | `menus.text_members` · `menus.front_end_art` | offline-writer-proved ×2 | 531 `TEXT` banks · 103 menu surfaces |
| The Crib | — | page note | an ESPN NFL 2K5 feature, not an NFL Street concept |
| Audio | `audio.streams` · `audio.banks` | extract-only ×2 | 679 streams (42 export) · 236 banks / 1,031 sounds |
| Gameplay | — | page note | no patch site located on `SLUS_208.41`; every site is per-title research |
| Playbooks & Plays | `playbooks.play_databases` | offline-writer-proved | 266 rows across six tables |
| All Textures | `textures.container_inventory` · `textures.mmap_census` | read-only-mapped · offline-writer-proved | 48 containers / 8,803 members · 1,048 surfaces |
| Saves | — | page note | progress lives on a memory card; nothing captured for this serial |
| Build & Share | core | — | the shell's own page |

Fifteen rows, eleven surfaces, every page answered.

---

## 4. The kit container, and why this page has no writer

`PLATEX.DAT` is 1,735 `MMAP` members in 25,126,912 bytes, one image each. **Of
those 1,735 images, 1 decodes.** The other 1,734 declare **pixel layout 6 (1,072
of them) or pixel layout 5 (662)**, and `mmap_art` reads two layouts: 0 (4-bit
indexed) and 1 (8-bit indexed) [M].
`docs/product/measured/nflstreet1_ps2/platex-pixel-layout-census.json` is the
per-member census.

**The assumption that would make that wrong** is that a kit texture on this disc
is an indexed texture. It is not: it is direct colour with no CLUT — which is
also why every one of the 1,170 distinct names PCSX2 wrote across six captured
frames declares **PSM 0 (PSMCT32)** and not one declares PSM 27 [M], and why
1,074 of those 1,170 pair with nothing this module indexes.

So the Uniforms page is `extract-only` and has no writer: a write lane there
would offer one target and refuse 1,734, which is a control that can only
refuse. **A decoder for pixel layouts 5 and 6 is the one thing this container is
waiting on** — not a bigger cap and not a longer walk. The disc's other 1,048
decodable surfaces do have writers, on their own pages.

There is also no kit *table* to pair the art with. The create-a-team tables that
would carry one — `UNIF`, `TUNI`, `GEAR`, `CRTM`, `TATO`, `HAIR`, `FACE`,
`LOGO`, `CPAL` and the rest, **96 tables in `TEMPLATE.DAT`** — describe a
*created* team, not one of the 32 shipped ones [M]. A shipped team's look is
these textures plus the three palette slots on its `TEAM` row.

---

## 5. PCSX2 texture identities

Six frames have been captured on this disc — the Select Field screen, and five
frames of gameplay. Pairing them against the disc with
`tools/ps2_texture_identities.py --game nflstreet1_ps2` named **33 disc
textures** from 87 of the 1,170 distinct dumped files (9 more paired on RGB but
not on alpha; 6 were ambiguous; 1,074 matched nothing) [M].
`docs/product/measured/nflstreet1_ps2/pcsx2-texture-identities.json` is the
table every art row in this module reads.

| container | indexed | **named** | frames that drew one |
|---|---|---|---|
| `UIS_INGM.DAT` | 18 | 10 | 4 |
| `ENVRNMT.DAT` | 15 | 5 | 6 |
| `IGDATA.DAT` | 8 | 5 | 1 |
| `UIS_BUTT.DAT` | 13 | 4 | 3 |
| `STATMOD.DAT` | 18 | 3 | 5 |
| `UIS_COMN.DAT` | 16 | 3 | 5 |
| `UIS_TMLO.DAT` | 102 | 2 | 3 |
| `PLATEX.DAT` | 1 | 1 | 5 |
| *fourteen others* | 862 | **0** | **0** |

Everything else is **derived** — computed from the texture's own bytes — and
`identity_note` says which of the two a name is, on every texture. **No
derivation check has been run for this disc**: 33 named textures is too small a
sample to measure a derivation rule against, and quoting Madden 09's or NCAA
09's figure here would be quoting another disc's measurement.

`extra_psms` is empty and that is measured, not inherited: all 1,170 dumped names
declare PSM 0, so no `PSMT8H` name exists in this capture to need the
linear-stream hash.

**What to capture next** is the last row of that table: `UIS_PORT.DAT`'s 549
portraits are by far the largest block no frame has drawn. §8 is the list.

---

## 6. What each writer costs, and what was proved on the real disc

Every writer is proved twice: on a synthetic disc in the conformance harness and
by hand on the retail image. The hand trial builds a NEW image, diffs it against
the source byte for byte, and checks that every changed byte lies inside a range
the receipt declared. Run on `/turret/builds/discs/ps2/NFL Street (USA).iso` [M]:

| lane | targets | bytes changed | runs | declared ranges | every change inside one | image same length | verifier |
|---|---|---|---|---|---|---|---|
| `players.team_databases` | 688 | 16 | 6 | 2 | yes | yes | **PASS** |
| `identity.team_records` | 160 | 10 | 4 | 2 | yes | yes | **PASS** |
| `menus.text_members` | 4,000 | 1,717 | 1 | 2 | yes | yes | **PASS** |
| `playbooks.play_databases` | 310 | 57,411 | 480 | 20 | yes | yes | **PASS** |
| `identity.logo_art` | 102 | 147,141 | 324 | 18 | yes | yes | **PASS** |
| `rosters.portrait_art` | 549 | 3,865 | 123 | 2 | yes | yes | **PASS** |
| `field_art.create_team_art` | 97 | 4,015 | 29 | 2 | yes | yes | **PASS** |
| `stadiums.playfield_art` | 34 | 142,695 | 603 | 18 | yes | yes | **PASS** |
| `presentation.screen_art` | 155 | 130,704 | 323 | 2 | yes | yes | **PASS** |
| `menus.front_end_art` | 103 | 21,098 | 1397 | 20 | yes | yes | **PASS** |
| `textures.mmap_census` | 891 | 3,865 | 123 | 2 | yes | yes | **PASS** |

An art trial is not a round trip: the exported PNG is edited first -- every pixel
of one colour already in the image repainted with another colour already in the
image, which re-indexes cleanly against the member's own CLUT -- so the writer
has to land a real difference inside its declared ranges. A plain round trip
re-encodes byte-identically on this stack, which proves the encoder is a faithful
inverse and proves nothing about where a change goes.

Two things the numbers say. `playbooks` and the `LZH1` art containers move far
more bytes than the stored ones because a change re-packs the whole member and
the container's directory and every cached copy of it move with it;
`DB_TEAMS.DAT`'s members are **stored**, which is why a roster edit moves 16
bytes and nothing else. And a **cached** `LZH1` member cannot be rewritten at
all: the first `LOADDATA.DAT` member this trial reached is copied into `FE.QKL`
and its re-pack came back 156,223 bytes against the 153,488 it replaced, so the
lane refused it by name -- *"a cached copy is a fixed slot, so this member cannot
be rewritten at a different size; nothing was written"* -- and the trial moved to
the next target. That refusal is the writer working, and it is why the shared
`mmap_art` encoder not reproducing EA's exact `LZH1` packing is a bound on which
members are writable rather than a bug.

**None of the four `TEXT` containers is named by any of the nine `QL01` caches**
[M], which makes a text edit the cheapest write in the module: no cached
directory and no cached member moves with it.

The full receipt for every row is
`docs/product/measured/nflstreet1_ps2/real-disc-writer-trials.json`.

---

## 7. What has not been proved

* **Nothing has been booted.** No rebuilt NFL Street container has been loaded in
  PCSX2 or on hardware. Every writer's evidence is offline.
* **No derivation check** for this disc's texture names (§5).
* **No PCSX2 pack** built from any of these names has been loaded.
* **`PPOS` 0..18 are numbers, not names.** What each position code means on this
  disc has not been established, so the editor offers the number.
* **`PWGT` and `PHGT` units** are not established; both are offered as the raw
  stored value (10..205 and 0..80 across the disc [M]).
* **`TMC1`/`TMC2`/`TMC3` are palette indices**, and the palette (`CPAL`, 128 rows
  in `TEMPLATE.DAT`) is not read by this module, so no colour is drawn.
* **The MicroTalk streams** — 637 of 679 — are listed and refused. No decoder for
  the codec exists in this repository or in ffmpeg.
* **`FNTS` fonts** are not decoded, so which glyphs a replacement string can draw
  is unknown.

---

## 8. Captures worth making

Ordered by how much they would confirm, from §5's "frames that drew one" column.

1. **The roster / player-select screen**, with a squad list showing portraits —
   reaches `UIS_PORT.DAT`, 549 indexed surfaces, **0 named**. The single
   largest unconfirmed block on the disc.
2. **The create-a-baller / create-a-team screens** — reaches `UIS_CRTM.DAT` (56)
   and, if the field editor is open, `UIS_FSEL.DAT` (41). Both at 0 named.
3. **A post-game results screen** and **an online-results screen** — reaches
   `UIS_ONRE.DAT`, 103 indexed, 0 named.
4. **A load screen held long enough to dump** — `LOADDATA.DAT`, 12 surfaces, 0
   named.
5. **The main menu at rest and one submenu** — `UIS_FRON.DAT` (11),
   `UIS_BGPL.DAT` (25), `UIS_BGMP.DAT` (3), `UIS_GABR.DAT` (11),
   `UIS_CHAL.DAT` (19), `UIS_CTRL.DAT` (4), `UIS_CWIN.DAT` (1) — 74 surfaces
   across seven containers, all at 0 named.
6. **A movie / cutscene frame** — `UIS_MOVI.DAT`, 22 surfaces, 0 named.

For the headless witness harness, a **savestate positioned one screen before each
of those loads** is what is wanted, not the screen itself — see
`docs/owner/SAVESTATE_QUEUE.md`. The two that matter most are (a) sitting on the
main menu with the roster screen one button away, and (b) sitting at the end of a
game with the results screen one advance away.

---

## 9. Running it without a window

```bash
python3 -m mod_editor.games.nflstreet1_ps2.inventory_lane --source DISC.iso
python3 -m mod_editor.games.nflstreet1_ps2.database_lane   --source DISC.iso
python3 -m mod_editor.games.nflstreet1_ps2.identity_lane   --source DISC.iso
python3 -m mod_editor.games.nflstreet1_ps2.playbooks_lane  --source DISC.iso
python3 -m mod_editor.games.nflstreet1_ps2.text_lane       --source DISC.iso
python3 -m mod_editor.games.nflstreet1_ps2.texture_lane    --source DISC.iso
python3 -m mod_editor.games.nflstreet1_ps2.art_pages --lane logos --source DISC.iso
python3 -m mod_editor.games.nflstreet1_ps2.audio_lane --lane streams --source DISC.iso

python3 tools/validate_game_lane.py --game nflstreet1_ps2 --all
python -m mod_editor.games conformance --game nflstreet1_ps2
```

Every one of them takes `--selftest` instead of `--source` and runs on a
synthetic disc, needing no game data.

# NFL Street 3 (USA, PlayStation 2) — the module

`SLUS-21482`. The eighth game on the Game Studio shell, and the second built
entirely out of shared lane bases — the same bases NFL Street uses, instantiated
with this disc's own container list and field map. Read
`docs/product/MODULE_AGENT_CHARTER.md` first; this page is the one module
document for this game.

**Evidence tags.** **[M]** measured on the retail disc this project holds; **[S]**
sourced from a named document; **[A]** assumed.

---

## 1. What the disc is

| | |
|---|---|
| Serial | `SLUS-21482` |
| Boot file | `SLUS_214.82`, 4,623,328 bytes |
| Boot ELF sha256 | `88fd27455a031f053cccb81b0e97ca32e2ea69fe0a941d4f5d21771d739aedfa` [M] |
| Image sha256 | `d80064ae58cb4da7a1f4cdc04b2bedcfb4fee6d91c0562bc1dc7a6670295124c` [M] |
| Image | 4,695,883,776 bytes, 158 files, 6 directories, 2048-byte sectors [M] |
| PCSX2 CRC | `E31B62CC` [M] |

Every shared reader opens it with nothing changed [M]:

| | |
|---|---|
| `TERF` containers | **80 of 80** open |
| Members | **27,178 of 27,178** |
| EA `TDB` databases | **47 of 47**, plus one bare database (`/DATA/STREAMED.DB`, 26 tables, 361 fields) |
| CRC-32/MPEG-2 slots | **1,038 of 1,038** already hold the value they recompute to |
| `MMAP` members | 17,986 |
| `TEXT` string banks | 813 |
| `SCHl` streams | 920 · `BNKl` banks 197, holding 691 sounds |
| Nested `TERF` members | 143 |
| `QL01` preload caches | **11** — `FE.QKL` and `GAME0.QKL`..`GAME9.QKL` |
| Preload copies | 2,295 copies of 49 containers; **2,294 byte-identical, 1 unresolved** |

The one unresolved copy is worth naming: `FE.QKL` names `PLAROSTERHAIR.DAT` and
no file of that name is on the disc, so that copy cannot be checked against
anything [M]. Nothing on this disc reads it and no lane here writes to it, but a
coherence check that silently ignored it would be claiming more than it measured.

`docs/owner/scoping/readiness/SLUS-21482.NFL-Street-3-USA.readiness.json` is the
census this table quotes.

---

## 2. NFL Street 3 is not a re-skin of NFL Street

Three years apart, same container family, **and no record schema survives except
one**. Measured by walking every TDB in `DB_TEAMS.DAT` and `IGDATA.DAT` on both
discs; the field-by-field census is
`docs/product/measured/nflstreet3_ps2/tdb-schema-difference.json` [M].

| table | NFL Street | NFL Street 3 | common names | same width | **same width *and* offset** |
|---|---|---|---|---|---|
| `PLAY` | 65 fields / 671 bits | **84 / 831** | 64 | 49 | **0** |
| `TEAM` | 41 / 575 | **22 / 447** | 21 | 20 | **0** |
| `DCHT` | 4 / 63 | 4 / 63 | 4 | 4 | **4** |
| `PBST` | 27 / 511 | **5 / 127** | 5 | 3 | 0 |
| `PBPL` | 4 / 63 | 5 / 255 | 4 | 1 | 0 |
| `PLYL` | 10 / 319 | 10 / 255 | 10 | 2 | 0 |
| `SETL` | 8 / 287 | 8 / 191 | 8 | 2 | 0 |
| `FORM` | 3 / 223 | 3 / 95 | 3 | 1 | 0 |
| `PBFM` | 5 / 479 | 9 / 191 | 5 | 1 | 0 |

**`DCHT` is the only table that ports byte for byte.** Everything else has to be
read from the file's own field directory, which is what the metadata-driven bases
do — so the same code opens both discs and no offset is spelled anywhere.

What this disc added:

* **Twenty `PLAY` fields**, almost all a create-a-baller face block — `PFEA`,
  `PFEB`, `PFEY`, `PFFH`, `PFHC`, `PFJC`, `PFLP`, `PFMO`, `PFNO`, `PFBW`,
  `PHDC`, `PJCT`, `PHTM`, `PSTM`, `PMED`, `PBTO`, `PLIL`, `PLPR`, plus `PJUM`
  and `TGTI`. **Every one of them is 0 on all 449 rows** [M]: the disc carries
  the schema and ships none of it filled in. `PAWR` is gone.
* **Fifteen fields widened**: `PFNA` 88→96 bits, `PLNA` 104→112, `PNKN`
  104→128, `PATO`/`PLTO`/`PRAT`/`PRLT`/`PSRT`/`PRFC` 6→8, `PSKI` 3→4,
  `SGT1`..`SGT4` 5→6, `PPNT` 6→7.
* **`PBFM.FAU1..FAU4`**, four audible slots, and a `name` on `PBPL` — so this
  disc's playbook page can rename a play slot directly where NFL Street's has to
  rename the play it calls.
* **`TEAM.CTDL`**, 1 bit, set on all 32 rows.

What it removed: **twenty `TEAM` fields**, including eleven per-position team
ratings (`TRQB`, `TRRB`, `TROL`, `TRDL`, `TRLB`, `TRDB`, `TRST`, `TWRR`) —
three survive (`TROF`, `TRDE`, `TROV`) — and **`PBST`'s entire route grid**, the
eleven `ax`/`ay` coordinate pairs that made NFL Street's `PBST` 27 fields.

**The rating scale is 0..100 here too.** `PBLK`, `PDFT`, `PJUM` and `PSPD` all
reach **100** across the 449 rows; the fields are 7 bits and would hold 127 [M].
`PAGE` is 0 on every row and `PRFC` is 255, its own ceiling, on every row;
neither is offered.
`docs/product/measured/nflstreet3_ps2/db-teams-value-ranges.json` is the census.

The disc is also simply bigger: 449 player rows against 402, 813 `TEXT` banks
against 531, 17,986 `MMAP` members against 2,785, and `PLATEX.DAT` at 16,259
members against 1,735 — **9.4x**.

---

## 3. The fourteen pages

| page | lane | rung | what it reaches |
|---|---|---|---|
| Uniforms & Equipment | `uniforms.texture_census` | extract-only | `PLATEX.DAT`, 16,259 members; **3 decode** — see §4 |
| Names, Numbers & Faces | `players.team_databases` · `rosters.portrait_art` | offline-writer-proved ×2 | 449 player rows · 693 portraits |
| Text & Team Identity | `identity.team_records` · `identity.logo_art` | offline-writer-proved ×2 | 32 `TEAM` rows · 346 logos and banners |
| Field Art & Create-Team Art | `field_art.create_team_art` | offline-writer-proved | 140 surfaces |
| Stadiums | `stadiums.playfield_art` | offline-writer-proved | 112 surfaces |
| Presentation | `presentation.screen_art` | offline-writer-proved | 312 surfaces |
| Menus & UI | `menus.text_members` · `menus.front_end_art` | offline-writer-proved ×2 | 813 `TEXT` banks · 114 menu surfaces |
| The Crib | — | page note | an ESPN NFL 2K5 feature, not an NFL Street concept |
| Audio | `audio.streams` · `audio.banks` | extract-only ×2 | 920 streams (27 export) · 197 banks / 691 sounds |
| Gameplay | — | page note | no patch site located on `SLUS_214.82` |
| Playbooks & Plays | `playbooks.play_databases` | offline-writer-proved | 702 rows across six tables |
| All Textures | `textures.container_inventory` · `textures.mmap_census` | read-only-mapped · offline-writer-proved | 80 containers / 27,178 members · 1,725 surfaces |
| Saves | — | page note | memory card; `/DATA/STREAMED.DB` is a presentation database, not a save |
| Build & Share | core | — | the shell's own page |

Fifteen rows, eleven surfaces, every page answered.

---

## 4. The kit container, and why this page has no writer

`PLATEX.DAT` is 16,259 `MMAP` members in 87,709,696 bytes, one image each. **Of
those 16,259 images, 3 decode.** The other 16,256 declare **pixel layout 5
(13,853 of them) or pixel layout 6 (2,403)**, and `mmap_art` reads two layouts:
0 (4-bit indexed) and 1 (8-bit indexed) [M].
`docs/product/measured/nflstreet3_ps2/platex-pixel-layout-census.json` is the
per-member census.

**The assumption that would make that wrong** is that a kit texture on this disc
is an indexed texture. It is not: it is direct colour with no CLUT — which is
also why every one of the 807 distinct names PCSX2 wrote across five captured
frames declares **PSM 0 (PSMCT32)** and not one declares PSM 27 [M].

So the Uniforms page is `extract-only` and has no writer: a write lane would
offer three targets and refuse 16,256. **A decoder for pixel layouts 5 and 6 is
the one thing this container is waiting on**, and it would serve both NFL Street
discs at once. The disc's other 1,725 decodable surfaces do have writers.

There is no kit *table* either. The create-a-team tables — `UNIF`, `TUNI`,
`GEAR`, `CRTM`, `FACE`, `TATO`, `CPAL` and the rest, **149 tables in
`TEMPLATE.DAT`** — describe a *created* team, not one of the 32 shipped ones [M].
And Street 3's twenty-field `PF*` face block on `PLAY` is zero on every row, so
even the per-player face indices are unused on the retail disc.

---

## 5. PCSX2 texture identities

Five frames have been captured on this disc — a loading screen carrying the
Audibles tip card, and gameplay. Pairing them with
`tools/ps2_texture_identities.py --game nflstreet3_ps2` named **28 disc
textures** from 81 of the 807 distinct dumped files (33 more paired on RGB but
not on alpha; 3 were ambiguous; 693 matched nothing) [M].
`docs/product/measured/nflstreet3_ps2/pcsx2-texture-identities.json` is the
table every art row reads.

| container | indexed | **named** | frames that drew one |
|---|---|---|---|
| `UIS_INGM.DAT` | 29 | 16 | 5 |
| `STATMOD.DAT` | 78 | 5 | 3 |
| `UIS_BNRT.DAT` | 173 | 2 | 5 |
| `UIS_BUTT.DAT` | 13 | 2 | 4 |
| `UIS_TMLO.DAT` | 173 | 2 | 4 |
| `PLATEX.DAT` | 3 | 1 | 3 |
| *nineteen others* | 1,259 | **0** | **0** |

The 33 RGB-only matches are the class the coordinator's note names: **confirmable
but never derivable**, because the game pads their palette at run time, so the
CLUT hash the derivation computes from the disc bytes is not the CLUT hash PCSX2
sees [A]. They are recorded as `rgb_only` in the document rather than counted as
a derivation failure.

Everything else is **derived**, and `identity_note` says which of the two a name
is, on every texture. **No derivation check has been run for this disc**: 28
named textures is too small a sample to measure a rule against.

`extra_psms` is empty and that is measured: all 807 dumped names declare PSM 0,
so no `PSMT8H` name exists in this capture to need the linear-stream hash.

---

## 6. What each writer costs, and what was proved on the real disc

Built on `/turret/builds/discs/ps2/NFL Street 3 (USA).iso`, diffed against the
source byte for byte, with every changed byte required to lie inside a range the
receipt declared [M]:

| lane | targets | bytes changed | runs | declared ranges | every change inside one | image same length | verifier |
|---|---|---|---|---|---|---|---|
| `players.team_databases` | 885 | 13 | 4 | 2 | yes | yes | **PASS** |
| `identity.team_records` | 160 | 7 | 3 | 2 | yes | yes | **PASS** |
| `menus.text_members` | 3,448 | 718 | 1 | 2 | yes | yes | **PASS** |
| `playbooks.play_databases` | 900 | 69,195 | 594 | 22 | yes | yes | **PASS** |
| `identity.logo_art` | 346 | 15,998 | 155 | 2 | yes | yes | **PASS** |
| `rosters.portrait_art` | 693 | 2,804 | 162 | 2 | yes | yes | **PASS** |
| `field_art.create_team_art` | 140 | 4,015 | 29 | 2 | yes | yes | **PASS** |
| `stadiums.playfield_art` | 112 | 120 | 8 | 2 | yes | yes | **PASS** |
| `presentation.screen_art` | 313 | 10,306,912 | 42589 | 24 | yes | yes | **PASS** |
| `menus.front_end_art` | 114 | 1,014 | 10 | 2 | yes | yes | **PASS** |
| `textures.mmap_census` | 1,425 | 2,804 | 162 | 2 | yes | yes | **PASS** |

An art trial is not a round trip: the exported PNG is edited first -- every pixel
of one colour already in the image repainted with another already in it -- so the
writer has to land a real difference inside its declared ranges.

`presentation.screen_art` moves 10.3 MB because the member it reached is in
`LOADDATA.DAT`, a 10,537,856-byte `LZH1` container: a change re-packs the member,
moves the directory, and every cached copy moves with it. `stadiums.playfield_art`
moves 120 bytes because the member it reached is stored. Both are inside their
declared ranges and both leave the image the exact length it went in.

**None of the six `TEXT` containers is named by any of the eleven `QL01` caches**
[M], which makes a text edit the cheapest write in the module.

The full receipt for every row is
`docs/product/measured/nflstreet3_ps2/real-disc-writer-trials.json`.

---

## 7. What has not been proved

* **Nothing has been booted.** No rebuilt NFL Street 3 container has been loaded
  in PCSX2 or on hardware.
* **No derivation check** for this disc's texture names (§5), and **no PCSX2
  pack** built from any of them has been loaded.
* **The `PF*` face block is unwritable in practice**, not because the lane cannot
  write it but because nothing on the retail disc reads a non-zero value there
  and this project has not established what one would do.
* **`PPOS` codes, `PWGT`/`PHGT` units and `TMC1..3` palette entries** are numbers
  whose meaning is not established, exactly as on NFL Street.
* **893 of 920 streams are MicroTalk** and are listed and refused by name.
* **`FNTS` fonts** are not decoded (19 font sets across three containers).
* **`/DATA/STREAMED.DB`** is catalogued by the inventory lane and no lane writes
  it; what its 26 tables drive has not been established.

---

## 8. Captures worth making

From §5's "frames that drew one" column, ordered by size of the unconfirmed
block.

1. **The roster / baller-select screen** — `UIS_PORT.DAT`, 693 indexed, **0
   named**. The largest unconfirmed block on the disc.
2. **A post-game results screen** — `UIS_POST.DAT`, 90 indexed, 0 named. This
   disc has a post-game container NFL Street does not.
3. **A load screen held long enough to dump** — `LOADDATA.DAT`, 68 surfaces, 0
   named (5.7x NFL Street's).
4. **The create-a-team and field editors** — `UIS_CRTM.DAT` (56),
   `UIS_FOOT.DAT` (51), `UIS_FSEL.DAT` (24), `UIS_CMAP.DAT` (9).
5. **The main menu at rest, one submenu, and a mini-game select** —
   `UIS_FRON.DAT` (36), `UIS_COMN.DAT` (17), `UIS_CHAL.DAT` (19),
   `MINIGAMP.DAT` (11), `UIS_MPIC.DAT` (11), `UIS_CTRL.DAT` (5),
   `CHNL_IMG.DAT` (2).
6. **A wider gameplay sweep** — `OBJMODEL.DAT` (26) and `ENVRNMT.DAT` (8) were
   not drawn by any of the five frames, which suggests the captured gameplay was
   on one playfield.

For the headless witness harness, the savestate wanted is **one screen before
each of those loads** (`docs/owner/SAVESTATE_QUEUE.md`): sitting on the team
select with the roster one button away, and sitting at the final whistle with the
results screen one advance away.

---

## 9. Running it without a window

```bash
python3 -m mod_editor.games.nflstreet3_ps2.inventory_lane --source DISC.iso
python3 -m mod_editor.games.nflstreet3_ps2.database_lane   --source DISC.iso
python3 -m mod_editor.games.nflstreet3_ps2.identity_lane   --source DISC.iso
python3 -m mod_editor.games.nflstreet3_ps2.playbooks_lane  --source DISC.iso
python3 -m mod_editor.games.nflstreet3_ps2.text_lane       --source DISC.iso
python3 -m mod_editor.games.nflstreet3_ps2.texture_lane    --source DISC.iso
python3 -m mod_editor.games.nflstreet3_ps2.art_pages --lane logos --source DISC.iso
python3 -m mod_editor.games.nflstreet3_ps2.audio_lane --lane streams --source DISC.iso

python3 tools/validate_game_lane.py --game nflstreet3_ps2 --all
python -m mod_editor.games conformance --game nflstreet3_ps2
```

Every one takes `--selftest` instead of `--source` and runs on a synthetic disc.

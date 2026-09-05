# Madden NFL 09 (PlayStation 2) — the four other art pages

**What this document is.** The uniform-art writer proved that an edited PNG can
go back into an `MMAP` member of a Madden 09 disc and come out again as the
pixels it was given. That writer was pointed at four containers. This document
is the other four pages it was pointed at afterwards: the **stadium art**, the
**field art**, every **menu, loading and overlay texture**, and the **player
and coach faces, tattoos and menu portraits**.

The code is `mod_editor/games/madden09_ps2/art_pages.py`. It contains no
decoder, no encoder and no writer: each of the four rows is
`uniform_art.UniformDiscArtWriteLane` with a different container list, page and
schema set. The lane class became container-parameterised to make that
possible; the uniform rows kept their containers, their schemas, their
classifications and their tests unchanged.

**Evidence tags.** **[M]** measured on the retail SLUS-21770 disc this box
holds; **[S]** sourced; **[A]** assumed.

**Retail-free.** Every number here is a count, a size or a digest. No member
byte, no palette entry and no decoded pixel is in this repository.

---

## 1. The four rows

| row | page | containers | texture members | decodable images | classification |
|---|---|---:|---:|---:|---|
| `madden09ps2.stadiums.textures` | Stadiums | 2 | 514 | 581 | `offline-writer-proved` |
| `madden09ps2.field_art.textures` | Field Art & Create-Team Art | 1 | 73 | 73 | `offline-writer-proved` |
| `madden09ps2.presentation.ui_textures` | Presentation | 50 | 7,678 | 6,482 | `offline-writer-proved` |
| `madden09ps2.rosters.face_textures` | Names, Numbers & Faces | 4 | 4,611 | 4,599 | `offline-writer-proved` |

8,449 of those images are distinct: `UIS_PLYR.DAT` is counted on two pages [M].

**One lane per row, not two.** The uniform page carries two rows because its
exporter shipped first and earns a lower rung than the writer that followed it.
These four ship with both halves at once, and one lane already *is* both: the
shell draws preview, **Export PNG** and a checked **Import PNG** out of
`decode_png` and `encode`, and **Build** writes the edited texture into a NEW
disc image. A second row per page would name the same code twice and give a
user two places to do one thing. That is the decision, and the evidence for it
is that the writer lane inherits every read method unchanged — there is nothing
an export-only row would add.

**`offline-writer-proved`, and never more.** Each row's receipt, plan and page
carry the same sentence: *no rebuilt Madden 09 container has been booted.*
Section 6 says exactly what a boot would settle.

---

## 2. What each page edits, and what it does not

### Stadiums — `STADIUMS.DAT`, `STADATA.DAT`

**Edits** the 514 `MMAP` texture members of the two stadium containers, 581 of
whose images decode [M].

**Does not edit** the **805 `SMF` and 2 `DMF` geometry members in the same two
containers** [M]. A stadium's shape, its stands, its scoreboard mesh and its
crowd are in those. **No decoder for `SMF` or `DMF` is built anywhere in this
repository and no layout for either is documented here**, so the catalogue
counts them by format per container and the lane leaves them alone. It is a
measured statement, not a plan: the members are there, they are counted, and
nothing here opens one.

**Does not know** which stadium a texture belongs to. Neither container names
its members; the member index is the only structure they offer [A].

Five members of `STADIUMS.DAT` — 828 to 832 — are **palette banks**: 45
alternate CLUTs each and **no surface at all**, so there are no pixels in them
to draw [M]. A palette bank is a real thing this format has, not a damaged
member, and the lane counts it, lists it and refuses it by name. Fifteen more
images declare no palette (member 822's ten 32x64 images and five 256x512
members, 823 to 827) and in `STADATA.DAT` 23 do; each is refused by name too,
rather than drawn wrong [M].

### Field Art & Create-Team Art — `FIELDART.DAT`

**Edits** the container's 73 `MMAP` textures, every one of which decodes: 69 at
128x128 and four at 1024x256 [M].

**Does not edit** the other **642 members, all `SMF` geometry** [M] — nine in
ten of the file. Same statement as the stadiums page: no decoder, no documented
layout, counted and left alone.

**Does not create a team.** The create-team art this page is also named for has
not been located on this disc by this project, and the page says so rather than
offering a control that could only refuse.

### Presentation — 48 `UIS_*.DAT`, `LOADDATA.DAT`, `ICONS.DAT`

**Does not edit the scorebug or the broadcast overlays.** They are drawn by the
executable from values it holds, not from a data file, and **nothing on this
disc has been mapped to them**. That was this page's whole note before these
rows existed and it is still true; what was wrong about it was the implication
that the page had nothing.

**Edits** the art those screens draw: 7,678 `MMAP` members across 50
containers, 6,482 of their images decodable [M]. 48 `UIS_*.DAT` files are on
the disc and **33 of them carry `MMAP` members**; the other 15 carry fonts
(`FNTS`), nested `TERF` containers, or members whose first 32 bytes match no
format id this reader knows [M].

Two measured answers rather than absences:

* **`ICONS.DAT` carries no `MMAP` member at all** — 21 unclassified members
  [M]. It is listed with what it holds.
* **`UIS_MCFL.DAT`'s 1,188 members** — the memory-card front-end textures —
  store their pixels under EA codec 4, `IPU1`, which nothing here decodes.
  They are refused by name at both ends, read and write [M]. A further 162
  images across the UI containers declare a pixel layout the decoder does not
  implement, 140 of them in `LOADDATA.DAT` [M].

`UIS_PLYR.DAT` is listed last so its 3,286 portraits do not fill the target
list ahead of every other menu texture; it is also on the faces page, which is
where a player portrait belongs.

### Names, Numbers & Faces — `PLYRFACE.DAT`, `COACFACE.DAT`, `TATTOOS.DAT`, `UIS_PLYR.DAT`

**Edits** 4,611 `MMAP` members: 532 player faces and 711 coach faces at
128x128, 82 tattoos, and 3,286 96x96 menu portraits. 4,599 decode; the 12 that
do not declare a pixel layout the decoder does not implement and are refused by
name [M].

**Does not edit** a player's name, number, team or ratings. Those are in the
`DB_TEAMS.DAT` databases the same page already lists table by table, and there
is no database writer.

**Does not know** which player a face or a portrait belongs to. Neither
container names its members [A].

The first three containers are **also** on the Uniforms & Equipment page, where
they have been since that lane shipped. One texture, two pages: a coach's face
is face art *and* part of the kit sheet a uniform editor wants beside it. An
edit through either row rebuilds the same container the same way.

---

## 3. The container inventory [M]

Counts from `python3 -m mod_editor.games.madden09_ps2.art_pages --page <page>
--source <iso>` over the retail disc; `named` is section 4. "other members" is
the read-only listing: nothing in that column is opened by any lane here.

#### Stadiums

| container | bytes | chunk | align | members | MMAP | other members | images | decodable | named |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|
| `STADIUMS.DAT` | 68,809,408 | COMP | 64 | 1,355 | 434 | 651 SMF, 270 empty | 510 | 490 | 76 |
| `STADATA.DAT` | 6,170,176 | COMP | 64 | 268 | 80 | 2 DMF, 154 SMF, 32 unclassified | 114 | 91 | 7 |
| **total** | | | | **1,623** | **514** | | **624** | **581** | **83** |

#### Field Art & Create-Team Art

| container | bytes | chunk | align | members | MMAP | other members | images | decodable | named |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|
| `FIELDART.DAT` | 7,380,032 | COMP | 64 | 715 | 73 | 642 SMF | 73 | 73 | 32 |
| **total** | | | | **715** | **73** | | **73** | **73** | **32** |

#### Presentation

| container | bytes | chunk | align | members | MMAP | other members | images | decodable | named |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|
| `UIS_ADAI.DAT` | 35,200 | DATA | 64 | 21 | 21 | -- | 21 | 21 | 0 |
| `UIS_ALL.DAT` | 10,236,016 | DATA | 4 | 34 | 0 | 34 TERF | 0 | 0 | 0 |
| `UIS_BANR.DAT` | 611,832 | COMP | 4 | 30 | 0 | 30 unclassified | 0 | 0 | 0 |
| `UIS_BGIM.DAT` | 6,368,064 | DATA | 64 | 101 | 101 | -- | 101 | 101 | 0 |
| `UIS_BGLO.DAT` | 25,280 | DATA | 64 | 7 | 7 | -- | 7 | 7 | 0 |
| `UIS_CCST.DAT` | 4,288 | DATA | 64 | 4 | 0 | 4 unclassified | 0 | 0 | 0 |
| `UIS_COAC.DAT` | 1,057,600 | DATA | 64 | 239 | 239 | -- | 239 | 239 | 0 |
| `UIS_COMN.DAT` | 193,408 | DATA | 64 | 98 | 98 | -- | 98 | 98 | 10 |
| `UIS_CSTY.DAT` | 448 | DATA | 64 | 3 | 0 | 3 unclassified | 0 | 0 | 0 |
| `UIS_CTLO.DAT` | 6,159,232 | DATA | 64 | 239 | 239 | -- | 239 | 239 | 0 |
| `UIS_FE.DAT` | 1,376,896 | DATA | 64 | 147 | 147 | -- | 147 | 147 | 0 |
| `UIS_FONT.DAT` | 147,648 | DATA | 64 | 10 | 0 | 10 FNTS | 0 | 0 | 0 |
| `UIS_FSTY.DAT` | 256 | DATA | 64 | 1 | 0 | 1 unclassified | 0 | 0 | 0 |
| `UIS_IG.DAT` | 155,392 | DATA | 64 | 67 | 67 | -- | 67 | 66 | 6 |
| `UIS_IGBN.DAT` | 98,372 | COMP | 4 | 6 | 0 | 6 unclassified | 0 | 0 | 0 |
| `UIS_IGMC.DAT` | 21,824 | DATA | 64 | 3 | 3 | -- | 3 | 3 | 0 |
| `UIS_IGTU.DAT` | 81,408 | DATA | 64 | 5 | 5 | -- | 5 | 5 | 0 |
| `UIS_LFLL.DAT` | 139,072 | DATA | 64 | 10 | 10 | -- | 10 | 10 | 0 |
| `UIS_LOAD.DAT` | 8,889,280 | DATA | 64 | 104 | 104 | -- | 104 | 104 | 0 |
| `UIS_MCFL.DAT` | 30,573,504 | DATA | 64 | 1,188 | 1,188 | -- | 1,188 | 0 | 0 |
| `UIS_MCIC.DAT` | 228,480 | DATA | 64 | 14 | 14 | -- | 14 | 14 | 0 |
| `UIS_MDRC.DAT` | 180,960 | COMP | 4 | 11 | 0 | 11 unclassified | 0 | 0 | 0 |
| `UIS_MEMC.DAT` | 74,920 | COMP | 4 | 6 | 0 | 6 unclassified | 0 | 0 | 0 |
| `UIS_NWPR.DAT` | 897,792 | DATA | 64 | 158 | 122 | 36 empty | 122 | 122 | 0 |
| `UIS_OMG.DAT` | 404,864 | DATA | 64 | 77 | 77 | -- | 77 | 77 | 0 |
| `UIS_PAUC.DAT` | 455,580 | COMP | 4 | 24 | 0 | 24 unclassified | 0 | 0 | 0 |
| `UIS_PAUS.DAT` | 466,372 | COMP | 4 | 28 | 0 | 28 unclassified | 0 | 0 | 0 |
| `UIS_PDAI.DAT` | 137,344 | DATA | 64 | 63 | 63 | -- | 63 | 63 | 0 |
| `UIS_PDBI.DAT` | 10,079,808 | DATA | 64 | 390 | 390 | -- | 390 | 369 | 0 |
| `UIS_PERS.DAT` | 1,763,712 | DATA | 64 | 52 | 52 | -- | 52 | 52 | 0 |
| `UIS_PMIL.DAT` | 12,288 | DATA | 2048 | 1 | 1 | -- | 1 | 1 | 0 |
| `UIS_POPS.DAT` | 973,204 | COMP | 4 | 60 | 0 | 60 unclassified | 0 | 0 | 0 |
| `UIS_PRGM.DAT` | 114,304 | DATA | 64 | 2 | 2 | -- | 2 | 2 | 0 |
| `UIS_PROL.DAT` | 194,560 | DATA | 64 | 78 | 78 | -- | 78 | 78 | 0 |
| `UIS_PRPS.DAT` | 203,932 | COMP | 4 | 16 | 0 | 16 unclassified | 0 | 0 | 0 |
| `UIS_SBLD.DAT` | 1,469,760 | DATA | 64 | 86 | 86 | -- | 86 | 86 | 0 |
| `UIS_SETT.DAT` | 66,488 | COMP | 4 | 4 | 0 | 4 unclassified | 0 | 0 | 0 |
| `UIS_SFPC.DAT` | 114,388 | COMP | 4 | 3 | 0 | 3 unclassified | 0 | 0 | 0 |
| `UIS_SLIV.DAT` | 910,976 | DATA | 64 | 285 | 285 | -- | 285 | 285 | 0 |
| `UIS_SMOD.DAT` | 1,482,752 | DATA | 2048 | 34 | 33 | 1 DMF | 33 | 33 | 0 |
| `UIS_SOLO.DAT` | 4,021,248 | DATA | 64 | 161 | 161 | -- | 161 | 161 | 0 |
| `UIS_STAD.DAT` | 1,595,328 | DATA | 64 | 49 | 49 | -- | 49 | 49 | 0 |
| `UIS_TIRL.DAT` | 479,680 | DATA | 64 | 84 | 52 | 32 empty | 52 | 52 | 0 |
| `UIS_TIRN.DAT` | 897,472 | DATA | 64 | 84 | 52 | 32 empty | 52 | 52 | 0 |
| `UIS_TMFN.DAT` | 552,192 | DATA | 64 | 60 | 60 | -- | 60 | 60 | 0 |
| `UIS_TMLL.DAT` | 4,982,912 | DATA | 64 | 285 | 285 | -- | 285 | 285 | 0 |
| `UIS_TMLO.DAT` | 1,493,120 | DATA | 64 | 285 | 285 | -- | 285 | 285 | 58 |
| `LOADDATA.DAT` | 2,480,960 | COMP | 64 | 17 | 16 | 1 TEXT | 170 | 30 | 0 |
| `ICONS.DAT` | 658,304 | DATA | 64 | 21 | 0 | 21 unclassified | 0 | 0 | 0 |
| `UIS_PLYR.DAT` | 13,308,032 | DATA | 64 | 3,286 | 3,286 | -- | 3,286 | 3,286 | 0 |
| **total** | | | | **8,041** | **7,678** | | **7,832** | **6,482** | **74** |

#### Names, Numbers & Faces

| container | bytes | chunk | align | members | MMAP | other members | images | decodable | named |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|
| `PLYRFACE.DAT` | 12,077,056 | DATA | 2048 | 532 | 532 | -- | 532 | 520 | 45 |
| `COACFACE.DAT` | 8,316,928 | COMP | 2048 | 711 | 711 | -- | 711 | 711 | 0 |
| `TATTOOS.DAT` | 226,496 | DATA | 64 | 82 | 82 | -- | 82 | 82 | 0 |
| `UIS_PLYR.DAT` | 13,308,032 | DATA | 64 | 3,286 | 3,286 | -- | 3,286 | 3,286 | 0 |
| **total** | | | | **4,611** | **4,611** | | **4,611** | **4,599** | **45** |

#### preload copies

| container | directory copies | member copies |
|---|---:|---:|
| `STADIUMS.DAT` | 3 | 1 |
| `STADATA.DAT` | 0 | 67 |
| `FIELDART.DAT` | 3 | 0 |
| `LOADDATA.DAT` | 1 | 1 |
| `PLYRFACE.DAT` | 2 | 29 |
| `COACFACE.DAT` | 2 | 4 |
| `TATTOOS.DAT` | 1 | 0 |
| `UIS_PLYR.DAT` | 3 | 1 |
| `UIS_COMN.DAT` | 0 | 86 |
| `UIS_IG.DAT` | 0 | 36 |
| `UIS_TMLO.DAT` | 2 | 3 |
| `UIS_TMFN.DAT` | 2 | 3 |
| `UIS_SLIV.DAT` | 3 | 3 |
| `UIS_PRGM.DAT` | 1 | 2 |
| `UIS_POPS.DAT` | 2 | 4 |
| `UIS_ALL.DAT` | 3 | 8 |
| `UIS_FONT.DAT` | 0 | 4 |
| `UIS_COAC.DAT` | 1 | 1 |
| `UIS_PERS.DAT` | 2 | 1 |
| `UIS_SOLO.DAT` | 2 | 1 |
| `UIS_TMLL.DAT` | 2 | 1 |
| `UIS_SMOD.DAT` | 1 | 0 |
| `UIS_BGIM.DAT` | 2 | 0 |
| `UIS_BANR.DAT` | 1 | 0 |
| `UIS_PAUC.DAT` | 1 | 0 |
| `UIS_PAUS.DAT` | 1 | 0 |

The preload table is load-bearing for the writer: `GAME.QKL` and `FE.QKL` carry
byte copies of these containers' directories and of individual members, and the
game preloads from those rather than from the container. A directory change is
mirrored into every cached copy; an edit to a carried member rewrites its cache
copy when the stored size is unchanged and is **refused by name** when it is
not.

### Catalogue cost [M]

Wall clock on one desktop, pure Python, warm page cache:

| page | containers | members walked | texture members | seconds |
|---|---:|---:|---:|---:|
| Stadiums | 2 | 1,623 | 514 | 7.5 |
| Field Art | 1 | 715 | 73 | 4.7 |
| Presentation | 50 | 8,041 | 7,678 | 19.3 |
| Names, Numbers & Faces | 4 | 4,611 | 4,611 | 41.8 |

**How the presentation page walks 8,041 members in twenty seconds.** A member
is classified from its **first 32 bytes** — `TerfContainer.member_format` asks
the codec for exactly that many and the codec stops there — and only a member
that says `MMAP` is unpacked in full and parsed. The `MMAP` tables are then
read straight from the member's own header offsets; **no pixel run is decoded
and no palette is read** to build a catalogue. That matters most where a
container is mostly not textures: `FIELDART.DAT` is 642 geometry members
against 73 textures and `STADIUMS.DAT` 651 against 434, so nine in ten of
`FIELDART.DAT` and two in three of `STADIUMS.DAT` are never decompressed. The
cost that remains is `LZH1` in pure Python over the members that *are*
textures, which is why the faces page — 711 `LZH1` coach faces — is the slowest
of the four despite walking half as many members as the presentation page.

---

## 4. PCSX2 replacement identities: what the 33 frames reached [M]

A replacement filename is `<tex0 hash>-<clut hash>-<bits>.png`, and both hashes
are computed by the emulator at draw time. No disc file carries them, so
`tools/madden09_ps2_texture_identities.py` learns them by pairing a texture
dump with the disc on **exact pixel equality**. The corpus is the one that
exists: **33 frames — 32 coin-toss screens covering both kits of all 32 teams,
and one pre-game captains frame** [M].

The shipped table was built over the six containers the uniform lane reads.
Extending the index to the **34 further containers these four pages cover**
(`STADATA.DAT`, `LOADDATA.DAT` and every `UIS_*.DAT` with decodable members)
indexed 6,681 more disc surfaces and paired them against the same 9,617 dumped
files. Result: **81 textures matched, of which 74 the first table already
carried and 7 are new, every one of them in `STADATA.DAT`** [M]. The seven are
in `docs/product/measured/madden09_ps2/art-page-texture-identities.json`, in
the same schema, and the lanes read both tables.

**Coverage per container, and why it is what it is:**

| container | textures listed | named | why |
|---|---:|---:|---|
| `STADIUMS.DAT` | 490 | 76 | the stadium the coin toss happens in |
| `STADATA.DAT` | 91 | 7 | ditto, found by the extended index |
| `FIELDART.DAT` | 73 | 32 | the field the coin toss happens on |
| `PLYRFACE.DAT` | 520 | 45 | the captains standing at midfield |
| `UIS_TMLO.DAT` | 285 | 58 | the team logos the coin-toss screen draws |
| `UIS_COMN.DAT` | 98 | 10 | common in-game furniture |
| `UIS_IG.DAT` | 66 | 6 | in-game overlay pieces |
| every other container | 6,826 | 0 | no dumped frame drew one |

**234 of the 8,449 distinct textures have a name.** That is a fact about the
capture, not about the disc: a coin-toss frame draws a stadium, a field, two
kits, two captains and a scoreboard, and it draws no menu, no loading screen,
no memory-card icon and no coach's face. **The field and stadium coverage is
therefore partial** — 76 of 490 stadium textures and 32 of 73 field textures —
and every other page is near zero. `replacement_identity` returns `None` for
the 8,215 textures no frame reached, and the page says *no PCSX2 dump has shown
this one* rather than inventing a filename that would never match.

Naming a texture is not the same as loading a pack. **No pack built from these
names has been loaded in an emulator**, which is why no row here offers a
*Write PCSX2 pack* step.

---

## 5. The real-disc trial [M]

Read-only source, scratch destinations, images deleted immediately after. Three
edits, chained so the third image carries all three: one stadium texture, one
field-art texture and one UI texture, each replaced by a **synthetic PNG**
painted as diagonal bands cycling that texture's *own* CLUT — so the write is
exactly representable and any pixel difference would be the writer's, not the
quantiser's.

| step | row | texture | size | re-pack | container | image |
|---|---|---|---|---|---|---|
| 0 | `stadiums.textures` | `STADIUMS.DAT:697:0` | 128x128 | `LZH1`, 17,516 → **654** bytes stored | 68,809,408 → 68,792,576 | 1,657,339,904 → 1,657,339,904 |
| 1 | `field_art.textures` | `FIELDART.DAT:647:0` | 128x128 | `LZH1`, 7,704 → **1,408** bytes stored | 7,380,032 → 7,373,696 | unchanged |
| 2 | `presentation.ui_textures` | `UIS_TMLO.DAT:1:0` | 64x64 | **stored**, 5,228 → 5,228 bytes | 1,493,120 → 1,493,120 | unchanged |

**Directories and caches.**

* Steps 0 and 1 rewrote a member of a `COMP` container under `LZH1`, which
  changed its stored size, which moved the container's directory. All **three**
  cached copies of each directory were rewritten: one in `GAME.QKL` and two in
  `FE.QKL`, 21,824 bytes each for `STADIUMS.DAT` and 11,584 each for
  `FIELDART.DAT`.
* Step 2's container is a plain `DATA` container with no codec table, so the
  replacement could only be **stored** — and at 5,228 bytes it was exactly the
  size it replaced, fitting the 5,248-byte slot the member already owned. The
  directory did **not** move. `UIS_TMLO.DAT` member 1 is itself carried in
  `GAME.QKL`, so **the member's own cache copy was rewritten**, 5,228 bytes at
  offset 4,297,664. Both coherence paths therefore ran on real bytes.
* **The image never grew.** All three destinations are 1,657,339,904 bytes, the
  length of the source. Declared ranges: 6 / 86,022,725 bytes, 6 / 24,593,349,
  and 4 / 12,740,133.

**Verdicts: PASS, PASS, PASS.** Each independent verifier re-derived the image
edit with its own ISO9660 decoder, compared every untouched member of every
rebuilt container byte for byte (1,354, 714 and 284 of them), re-read every
preload-cache copy off the new image and compared it with what it copies (4, 3
and 5), checked each container against the layout rules the retail containers
follow, and decoded the rewritten texture out of the **new** image: 16,384 /
16,384, 16,384 / 16,384 and 4,096 / 4,096 pixels exact, **maximum channel error
0** in all three.

All three textures have a PCSX2 name, so a user who took the pack route instead
would know what to call the file:
`751f64bcd5fe6e5e-228d563e63748a9b-00001dd3.png`,
`667cff49f7fdcfca-a8cb3d42dc4a72ed-00001dd3.png` and
`ac2fc49f2e03da27-5ffc7a5e8bc3faa0-00001993.png`.

---

## 6. What still needs a boot

Nothing above says the game loads any of it. The trial proves the bytes; only a
console or an emulator can prove the game. **The owner does this, on the rig,
with a disc rebuilt by these lanes:**

1. **The stadium texture.** Start a game in the stadium whose art was edited
   and look for the synthetic bands. It also settles the open question in
   section 2: which member belongs to which venue is not established here, and
   an edit that shows up in one stadium and not another answers it.
2. **The field art.** Same disc, same game: the field is drawn from
   `FIELDART.DAT`, and the edited member is one of the 32 a coin-toss frame
   drew, so it should be visible at the coin toss without playing a down.
3. **The UI texture.** `UIS_TMLO.DAT` member 1 is a team logo the coin-toss
   screen draws. It is also carried in `GAME.QKL`, so seeing it change is the
   thing that proves the **member-copy cache rewrite** is right — if the game
   preloads the stale copy, the old logo appears and the edit is silently
   ignored.
4. **The negative that matters.** The game must still *load*: a directory
   rewritten in three cached copies is the step most likely to hang a preload
   rather than draw the wrong picture. A disc that boots to the menu and starts
   a game is the evidence; a disc that hangs names the step.

Until those are recorded, every row stays `offline-writer-proved` and every
receipt keeps the sentence that says so.

**Also unproved, and not on the boot list:** whether PCSX2 loads a replacement
pack built from the 234 names in section 4. That is a different route and a
different row, and no pack has been loaded.

---

## 7. Where the code is

| file | what it holds |
|---|---|
| `mod_editor/games/madden09_ps2/art_pages.py` | the four container lists, the parameterised lane, the synthetic-disc builder, the CLI |
| `mod_editor/games/madden09_ps2/uniform_art.py` | the lane itself: catalogue, decode, encode, write-back, verify. Container-parameterised; the uniform rows are its defaults |
| `mod_editor/games/madden09_ps2/mmap_art.py` | the `MMAP` layout: parse, decode, index, encode |
| `mod_editor/games/madden09_ps2/containers.py` | the disc, the `TERF` containers, the preload caches, the synthetic parts |
| `mod_editor/games/_formats/ea_terf.py` | the container format and both codecs |
| `tools/ps2_iso9660_writer.py`, `tools/ps2_iso9660_verify.py` | the image writer and the independent verifier |
| `docs/product/measured/madden09_ps2/art-page-textures.json` | the inventory in section 3, with the catalogue digests |
| `docs/product/measured/madden09_ps2/art-page-texture-identities.json` | the seven identities the extended index found |
| `tests/mod_editor/test_madden09_ps2_art_pages.py` | 33 tests, synthetic data only |
| `tools/validate_madden09_ps2_art_pages.sh` / `.bat` | the validator both rows name |

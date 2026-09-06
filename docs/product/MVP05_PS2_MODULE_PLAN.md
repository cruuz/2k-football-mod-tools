# MVP Baseball 2005 (PlayStation 2) — the module plan

This is a **plan**, not a module. Nothing is registered: there is no
`mod_editor/games/mvp05_ps2/`, no registry row, no allowlist entry and no
capability claimed. What exists today is two shared readers —
`mod_editor/games/_formats/ea_big.py` and `ea_shps.py`, documented in
`EA_BIG_FORMAT.md` and `EA_SHPS_FORMAT.md` — and the measurement below, taken
with them. The module scaffold follows once this plan is accepted.

**Why this disc needs its own readers.** MVP Baseball 2005 shares no container
with anything the fork already opens. It has **no `TERF` container and no EA
`TDB` database anywhere** [M]: every asset is inside an EA `BIG` archive, and
every texture inside those is an `SHPS` image bank. `ea_terf`, `ea_tdb` and
`madden09_ps2/mmap_art.py` are all inapplicable. `ea_schl` is the one thing
that carries over, and it carries over completely.

**Evidence tags.** **[M]** measured by running these readers against the retail
disc, read-only, over SSH on the test rig. **[S]** sourced — the owner's
independent disc mapper, cited where the two agree. **[A]** assumed.

**Retail-free.** Counts, archive and entry names, offsets and digests. No
payload, no decoded pixel and no string from the game.

---

## 1. The disc [M]

| field | value |
|---|---|
| image | `MVP Baseball 2005 (USA).iso`, 4,300,275,712 bytes, 434 files / 30 dirs, 2048-byte sectors |
| boot file / serial | `SLUS_211.35` / **SLUS-21135** |
| boot ELF | `/SLUS_211.35`, 8,130,840 bytes, sha256 `14db3aa3660e526ce12423db8102ce138e34f252985543406ff67a753e5c4615` |
| second executable | `/NTGUI_NA.ELF`, 4,815,512 bytes, sha256 `57d0cbda1cb1f66cfff2a1e9ab3821d38d449ce6fe01653db498cf4484b53985` |
| IOP modules | 44 `.IRX` under `/IOP` and `/NETGUI/IOPMODS` |
| whole-image sha256 | `90ed5e7974fc6f4374b43f6de19a984609c75dde94bc632a2f0940f8267b6484` [S] |
| PCSX2 CRC | `0544E001` [S] |

The boot-ELF digest was recomputed here and equals the mapper's [M].

---

## 2. The archive census [M]

**211 EA `BIG` archives, 43,773 entries.** Sixteen further files are *named*
`.BIG` and are not archives: eight are bare `SCHl` audio streams and eight are
their fixed-width index files. The reader refuses each by name.

| measure | value |
|---|---:|
| archives | 211 |
| entries the archives declare | 43,773 |
| nested archives, one level down | 643, declaring 2,423 more entries |
| entries at every depth | 46,196 |
| RefPack-packed entries | 23,855, in 194 archives |
| RefPack bytes produced, all of them, none refused | 764,038,770 |
| `SHPS` image banks, every depth | 16,371 |
| payload bytes across the archives | 633,933,782 |
| entries whose slot has 4 bytes of slack or more | 2 of 43,772 |

Entry formats at every depth: `SHPS` 16,371 · unclassified 13,933 · `SCHl`
9,123 · `ELF` (IOP objects) 4,077 · `TEXT` 2,044 · `BIGF` 643 · `FNTS` 2 ·
`BNKl` 2 · empty 1.

### The archives a page would name

| archive | payload bytes | entries | packed | `SHPS` banks | what it feeds |
|---|---:|---:|---:|---:|---|
| `/DATA/MODELS.BIG` | 122,840,084 | 2,505 | 2,505 | 1,407 | models with their textures [A] |
| `/DATA/GHEAD.BIG` | 107,294,846 | 8,400 | 8,400 | 8,400 | head textures [A] |
| `/DATA/FRONTEND/PORTRAIT.BIG` | 15,935,240 | 2,393 | 2,391 | 2,391 | portraits [A] |
| `/DATA/APTANIMS/EASOAPT.BIG` | 13,433,878 | 659 | 0 | 0 | the EA Nation dashboard: 641 nested archives, 14 `.loc`, 2 `.ttf` |
| `/DATA/ANIMS/ANIMS.BIG` | 8,940,627 | 730 | 0 | 0 | 244 `.axt` animation scripts + 243 `.ord`/`.orl` pairs |
| `/DATA/FRONTEND/BKGNDS.BIG` | 8,482,094 | 107 | 105 | 105 | menu backgrounds [A] |
| `/DATA/FRONTEND/STADIUMS.BIG` | 7,723,281 | 93 | 91 | 91 | ballpark menu art [A] |
| `/DATA/FRONTEND/UNIFORMS.BIG` | 2,963,017 | 557 | 555 | 555 | team kits [A] |
| `/DATA/DATAFILE/DATAFILE.BIG` | 2,832,470 | 460 | 460 | 0 | 460 four-line `.txt` tables |
| `/DATA/FRONTEND/LOGOS.BIG` | 1,652,990 | 132 | 132 | 132 | team logos [A] |
| `/DATA/DATABASE/DATABASE.BIG` | 1,010,268 | 18 | 18 | 0 | **the rosters** (§3) |
| `/DATA/FRONTEND/FRONTEND.BIG` | 673,890 | 196 | 192 | 0 | 196 `.fel` menu layout scripts |
| `/DATA/FRONTEND/FIELDS.BIG` | 252,497 | 58 | 56 | 56 | field art [A] |
| `/DATA/STADIUM/*.BIG` (87 of them) | — | 8,439 | 8,247 | 2,175 | one ballpark per lighting condition |

Grouped: 96 `/DATA/FRONTEND` archives (4,205 entries, 3,836 banks), 87
`/DATA/STADIUM` archives, 59 single-image `LOADn.BIG` loading screens, 12
`/DATA/AUDIO` archives (18,279 entries), 5 database/datafile archives.

---

## 3. Where the rosters live, and in what format [M]

**`/DATA/DATABASE/DATABASE.BIG`: eighteen RefPack-packed entries, and every
one of them is plain ASCII comma-separated text.** Not a TDB, not a
bit-packed table, not a binary record at all — the disc ships its rosters as
CSV. Each file's first line is a header naming the columns; every subsequent
line is one row prefixed with its own index, so a data line carries one comma
more than the header does. "Lines" below counts the header; "columns" counts
the names on it.

| entry | lines | columns | what its shape says it is [A] |
|---|---:|---:|---|
| `attrib.dat` | 2,923 | 47 | one row per position player, 46 attributes |
| `lhattrib.dat` / `rhattrib.dat` | 2,923 | 29 / 30 | the same players split by pitcher handedness |
| `pitcher.dat` | 1,432 | 30 | one row per pitcher |
| `bstats.dat` / `fbstats.dat` | 2,923 | 7 | batting lines |
| `lhbstats.dat` / `rhbstats.dat` | 2,923 | 15 | batting split by handedness |
| `pstats.dat` | 1,432 | 16 | pitching lines |
| `lhpstats.dat` / `rhpstats.dat` | 1,432 | 14 | pitching split by handedness |
| `career.dat` | 2,923 | 10 | career batting |
| `careerp.dat` | 1,432 | 12 | career pitching |
| `roster.dat` | 2,972 | 11 | the player ↔ team assignment |
| `team.dat` | 128 | 56 | one row per team, majors and minors |
| `tstat.dat` | 128 | 6 | team lines |
| `org.dat` | 36 | 15 | organisations |
| `manager.dat` | 36 | 22 | managers |

Three more archives sit beside it and are also CSV: `SCHEDULE.BIG` (9 packed
schedules, 333–5,494 lines of 5 or 6 fields), `PROGRESS.BIG` (8 **uncompressed**
CSVs — progression and contract curves) and `ROOKIE.BIG` (26 packed CSVs — the
draft-class generator's distributions). `/DATA/DATABASE/HIST.DAT` is a loose
299,729-byte binary whose first word is `0x00002ED5`; it is not parsed [A].

**What this means for the module.** The identity and ratings work that costs a
TDB reader, four CRCs and a bit-field map on the Madden side costs a CSV
parser here. The hard part moves entirely to the container: a row edit changes
the file's length, and §6 is why that is the wall.

---

## 4. Audio [M]

`ea_schl` — already in the fork, already proved on Madden 09 — reads this disc
without a change.

| where | streams | codec |
|---|---:|---|
| `SPCH_PA/PNAMEDAT.BIG`, `SPCH_PA/TNAMEDAT.BIG`, `SPCH_PBP/PNAMEDAT.BIG`, `SPCH_PBP/TNAMEDAT.BIG`, `SPCH_PBP/STDNMDAT.BIG` | 9,123 | MicroTalk (codec 4), mono, 24 kHz |
| `/DATA/AUDIO/SPCH_PA/PADAT.BIG`, `SPCH_PBP/PBPDAT.BIG` | 2 bare streams, 390 MB | MicroTalk (codec 4), mono, 24 kHz |
| `CHANTDAT.BIG` (144 MB), `RALLYDAT.BIG`, `PLCHTDAT.BIG`, `BDCSTDAT.BIG`, `HSFXDAT.BIG`, `STDMDAT.BIG` | 6 bare streams | **EA-XA ADPCM (codec 10)**, 1–2 channels, 24 kHz |
| 31 loose `SCHl` files | 31 | 29 EA-XA (stereo 32 kHz and 24 kHz, mono 24 kHz), 2 MicroTalk |
| `/DATA/AUDIO/ORCA/*.BNK`, `*.GEN` | 2 `BNKl` banks | parsed: 6 and 5 sounds |
| loose containers not yet opened | 42 `MPCh`, 24 `ABKC` | — |

So the answer to "is there EA-XA/PS ADPCM music" is **yes**: the broadcast
music, the crowd chants, the rally and stadium beds and the home-run effects
are all codec 10, which `ea_schl.decode_eaxa` decodes and
`ea_schl.encode_eaxa_blocks` can write. Speech is MicroTalk, for which no
decoder exists anywhere; it is listed and refused, exactly as on Madden 09.

Two CSV archives describe the audio rather than carry it: `SPEECHDB.BIG` (12
event tables) and `CROWDDB/AUDIOCSV.BIG` (21).

---

## 5. Text [M]

- **3 loose `LOCH` containers**: `/DATA/FEENG.LOC` (415,508 bytes),
  `/DATA/IGENG.LOC` (59,432), `/DATA/MC_ENG.LOC` (6,536). All three open with
  the same 20-byte header shape. **No reader exists**; only the magic and that
  header are measured.
- **14 `.loc` files** inside `EASOAPT.BIG`, plain `KEY=value|` text, one per
  dashboard language.
- **329 `.fel` files** across `FRONTEND`, `INGAME`, `COOPLAY`, `MINIGAME`,
  `APT` and `TITLE`: plain text, versioned (`VR:6`, `VR:7`), comma-separated,
  23 to 376 lines. These are the menu layout scripts. The grammar is not
  decoded.
- **460 `.txt`** in `DATAFILE.BIG`: four lines each, hex-valued, no commas.
- **244 `.axt`** animation scripts in `ANIMS.BIG`, plain text with `[Ver…`
  section headers.
- **12 `.sfn` fonts** (2 with an `FNTS` magic, 10 without) and 2 `.ttf`.

---

## 6. The wall, stated once [M]

Everything below is bounded by one measurement from `EA_BIG_FORMAT.md` §6:

> **An entry's slot is its own size plus at most three bytes.** Of MVP's
> 43,772 non-empty entries, 25,946 have zero slack and only two have four
> bytes or more.

So a writer for this disc has exactly one bounded shape — replace an entry's
payload in place, no larger than it was, rewriting its four-byte size word —
and for 23,855 of those entries "no larger than it was" means **after RefPack
compression**, which needs an encoder this project does not have. Growing an
entry, or renaming one, relocates every payload after it and rewrites every
table row from that point on.

**No checksum was found** in the archive header, the entry table or any
entry [M]; that negative is only as good as the search, because no rebuilt
archive has ever been loaded by the game.

That is why **no page below is above `extract-only` today**, and why the first
piece of engineering after this plan is accepted is the same for every page:
the bounded `BIG` entry writer plus a RefPack encoder, with an independent
verifier that re-derives the archive rather than importing the writer.

### 6.1 The second wall: `SHPS` code `0x0E` [M]

The art pages have a wall of their own, and it decides their rungs.
`EA_SHPS_FORMAT.md` §5: code `0x0E` is a **fixed-rate compressed codec** — 6
bytes per 4×4 block, exact at every size across 7,996 images, with
near-uniform bytes at every position mod 6, 8 and 12 — and nothing here
decodes it.

It is not a corner case. **Every uniform, every portrait, every head texture,
every one of the 59 loading screens, all of the field art, all of the
ballpark-builder art, all of the ballpark menu art and all of the awards art
is `0x0E`** [M]. What *is* decoded is the other side of the same disc: 8-bit
indexed (`0x02`) menu widgets, model textures and 80% of the in-park
textures, and 32-bit direct (`0x05`), which is the logo bank.

Disc-wide, 19,223 of 27,485 sampled images decode — **70%** — and of the 178
archives that hold banks, 5 decode every image, 78 decode none and 95 are
mixed [M].

---

## 7. The fourteen pages

The shell draws the same fourteen for every game (`PAGE_ORDER`,
`mod_editor/games/contract.py`). Here is what each would be for a baseball
game, the rung the readers earn **today**, and what a writer needs.

### 7.1 Uniforms & Equipment — `read-only-mapped`

`/DATA/FRONTEND/UNIFORMS.BIG` (557 entries, 555 `SHPS` banks) is the team
kits; `COOPUNIS.BIG` (127 / 124) is the create-a-team set. Every bank in both
opens, every image is listed with its dimensions and its palette — **and not
one of them decodes**: the kits are code `0x0E` and the rest are the 1×1
`0x01` stubs [M]. This page is filed at `read-only-mapped` for that reason and
no other; it is a texture page that can name every texture and show none.
**What lifts it**: the `0x0E` codec, §6.1. Only then the writer chain — the
bounded entry rewrite, a RefPack encoder (555 of 557 are packed) and an
`SHPS` encoder.

### 7.2 Names, Numbers & Faces — `extract-only` for the rosters, `read-only-mapped` for the faces

Two halves that earn different rungs, and the page should say so rather than
average them.

**The rosters come out whole.** `DATABASE.BIG`'s eighteen CSVs (§3) are the
identity, the ratings and the team assignment of every player on the disc, and
they are text. **Writer needs**: only the bounded entry rewrite and a RefPack
encoder — but a row edit changes the file's length, so "no larger than it was"
is a real constraint the editor has to enforce.

**The faces do not.** `PORTRAIT.BIG` (2,391 banks) and `GHEAD.BIG` (8,400 head
textures) are 100% code `0x0E` in every bank sampled [M]. Listed, never shown.
**What lifts it**: §6.1.

### 7.3 Text & Team Identity — `read-only-mapped`

Team names, cities and abbreviations are columns of `team.dat` and `org.dat`
(§3) — extractable today. The **UI strings** are the three `LOCH` files, and
`LOCH` has no reader in this project: its magic and 20-byte header are all
that is measured. **Writer needs**: a `LOCH` reader first, then the same
container work. Filed at the lower of the two rungs on purpose.

### 7.4 Field Art & Create-Team Art — `read-only-mapped`

`/DATA/FRONTEND/FIELDS.BIG` (58 entries / 56 banks) plus the seven ballpark-
builder archives — `BPSETUP` (39/37), `BPITEMS` (35/33), `BPUPGRAD` (37/35),
`BPTICKET` (26/24), `BPPROMOS` (18/16), `BPVENDOR` (18/16), `BPATTRAC` (9/7).
**All 224 of those images are code `0x0E`** [M], so the page can inventory
every one and decode none. **What lifts it**: §6.1.

### 7.5 Stadiums — `extract-only`

87 `/DATA/STADIUM/*.BIG` archives, one per ballpark per lighting condition,
each holding 97 entries in a fixed shape: 31 `.ord` IOP objects, 31 `.orl`
relocation files, 25 `SHPS` banks and 10 text files (`.dat`, `.csv`, `.ifo`).
Plus `FRONTEND/STADIUMS.BIG` (91 banks) and `BKGNDS.BIG` (105) for the menu
art.

**This is the art page that decodes best**, and the reason is the inverse of
§7.1: 10,182 of the 12,737 in-park images sampled are `0x02` and come out —
roughly 80% of every park [M]. What does not is the crowd and wall art
(`cram.ssh`, code `0x0E`) and, awkwardly, the whole of `STADIUMS.BIG`, the
ballpark *menu* art, which is 100% `0x0E` [M]. The geometry (`.ord`/`.orl`) is
unparsed as well. **What lifts it**: §6.1 for the crowd and the menu art; a
model reader for the geometry.

### 7.6 Presentation — `extract-only`

The scorebug and broadcast overlays are `INGAME.BIG`'s 44 `.fel` layout
scripts plus `IGONLY.BIG` and `COOPOV.BIG` (4 banks each, 137 images each, 123
of them `0x02` and decoded) [M]. The art comes out; **the `.fel` grammar is not
decoded**, so where a value on screen comes from is unknown. Same honest
position as Madden 09's presentation page, for a different reason.

### 7.7 Menus & UI — `extract-only`

The largest art surface on the disc: 641 nested `.apt`/`.const` dashboard
screens inside `EASOAPT.BIG`, 329 `.fel` layout scripts, 59 single-image
`LOADn.BIG` loading screens, `SPLASH`, `TITLE`, `LOGOS` (132 banks),
`AWARDS` (20), `MINIBAT`, `MINIPIT`, `SHARED`, `EASOART`, `FEONLY`, `SUONLY`.

The widget art decodes — `MINIBAT`, `MINIPIT`, `SHARED`, `EASOART` and
`BKGNDS` are 100% `0x02`, `FEONLY` 80% and `SUONLY` 89% — and the **team logo
bank is the disc's only 32-bit-direct art**: 396 of `LOGOS.BIG`'s 920 images
are code `0x05` and decode, the other 524 are `0x0E` [M]. **All 59 loading
screens are `0x0E` and none decodes** [M]. The layout scripts and the `.apt`
screens are listed, not parsed.

### 7.8 The Crib — **empty by design**

The Crib is an ESPN NFL 2K5 feature and not an MVP concept, so this page stays
empty here for the same reason it does on Madden 09. The nearest thing on this
disc — Owner Mode's ballpark builder — is art, and it is filed on
§7.4 where it belongs rather than given a page of its own.

### 7.9 Audio — `extract-only`

§4. EA-XA (codec 10) decodes today with `ea_schl`, which is proved on another
disc and needs no change for this one; the two `BNKl` banks parse. MicroTalk —
9,123 archived speech entries and the 390 MB commentary pair — is listed and
refused by name, because no decoder for it exists anywhere. **Writer needs**: the bounded
entry rewrite for the archived speech; the six bare-`SCHl` containers are
whole ISO9660 files rather than archive entries, so they are the one surface on
this disc where a same-length replacement does **not** need the `BIG` writer —
which makes them the cheapest first writer on the disc.

### 7.10 Gameplay — `unknown`

`/SLUS_211.35` (8,130,840 bytes, digest in §1), 44 IRX modules, `/DATA/MAT.BIG`
and `MISCMOD.BIG`'s 14 `.o` objects, and `/DATA/OVLAY_C.BIG`'s three
RefPack-packed entries, whose unpacked heads are MIPS prologue words [A]. The `CodePatchLane` shape and
`PS2_CODE_PATCH_PIPELINE.md` apply unchanged; **no translation has been made**,
so this page is a scaffold with nothing on it. Not "not built" — not started.

### 7.11 Playbooks & Plays — `extract-only`, and the page is renamed

**Baseball has no playbook, and the disc confirms it**: there is no play
archive, no formation table and no `.ord` that reads as one. What the page
would hold instead is the tuning that decides how the game plays, and that is
measured and it is text:

- `ROOKIE.BIG` — 26 CSVs, the draft-class generator's distributions (pitch
  velocity by star level, height, weight, body type, secondary position,
  handedness, hitting tendency, discipline, pickoff, knuckleball, hot/cold
  zones, and a 1,991-row two-column name table);
- `PROGRESS.BIG` — 8 **uncompressed** CSVs, the progression and contract curves
  by age and star level;
- `SPEECHDB.BIG` and `AUDIOCSV.BIG` — 33 CSVs of situational event tables;
- `DATAFILE.BIG` — 460 four-line hex tables, one pair per day/night variant.

Every one of them extracts today. `PROGRESS.BIG`'s eight are the only
uncompressed entries in any of these archives, which makes them the **second**
cheapest first writer on the disc: no RefPack encoder needed, only the bounded
size rule.

### 7.12 All Textures — `extract-only`

The inventory over every `SHPS` bank on the disc: 16,371 banks, and in a
4,665-bank sample 27,485 images of which 19,223 decode. The page's honest
number is the refusal: **of the 27,485 images in the sample, 7,996 code-`0x0E` and 321 code-`0x01`
are listed with their dimensions and refused by name**, and the refusal quotes the
measurement rather than saying "unsupported".

### 7.13 Saves — **out of scope**

An MVP Baseball 2005 memory-card save is not the disc. Same scope boundary as
Madden 09, stated the same way.

### 7.14 Build & Share — the shell's own page

Nothing game-specific.

### The fourteen in fourteen lines

| page | feeding containers | rung today |
|---|---|---|
| Uniforms & Equipment | `UNIFORMS.BIG` 555 banks, `COOPUNIS.BIG` 124 — every kit is the refused `0x0E` | `read-only-mapped` |
| Names, Numbers & Faces | `DATABASE.BIG` 18 CSVs come out; `PORTRAIT.BIG` 2,391 and `GHEAD.BIG` 8,400 are 100% `0x0E` | `extract-only` / `read-only-mapped` |
| Text & Team Identity | `team.dat`/`org.dat`; 3 `LOCH` files with no reader | `read-only-mapped` |
| Field Art & Create-Team Art | `FIELDS.BIG` 56 banks + 7 ballpark-builder archives, all 224 images `0x0E` | `read-only-mapped` |
| Stadiums | 87 park archives, ~80% of each decodes; the crowd banks and all menu art are `0x0E` | `extract-only` |
| Presentation | `IGONLY.BIG` 123 of 137 images decode; the `.fel` grammar is unknown | `extract-only` |
| Menus & UI | widget banks and 396 `0x05` logos decode; all 59 loading screens are `0x0E` | `extract-only` |
| The Crib | — | empty by design |
| Audio | 9,123 archived MicroTalk entries + 2 bare MicroTalk containers (refused) + 35 EA-XA streams + 2 `BNKl` | `extract-only` |
| Gameplay | `/SLUS_211.35`, 44 IRX, 3 packed overlays | `unknown` |
| Playbooks & Plays | `ROOKIE.BIG` 26 + `PROGRESS.BIG` 8 + 33 audio CSVs + 460 `.txt` | `extract-only` |
| All Textures | 16,371 `SHPS` banks; 19,223 of 27,485 sampled images decode, 8,317 refused by name | `extract-only` |
| Saves | — | out of scope |
| Build & Share | — | the shell's own |

---

## 8. What the first release would contain

A first `mvp05_ps2` module, built on this plan and nothing more, would ship:

1. **Identity** — `Ps2DiscIdentifier` over SLUS-21135 and the boot-ELF digest
   in §1, refusing any other disc with a sentence.
2. **Two read-only lanes**, the two the readers actually earn:
   `mvp05ps2.textures.bank_inventory` (`read-only-mapped`: every archive,
   every bank, every image, with the `0x0E` and `0x01` refusals quoted) and
   `mvp05ps2.rosters.database_export` (`extract-only`: the 18 CSVs out as
   text, plus `SCHEDULE`, `PROGRESS` and `ROOKIE`).
3. **Two art export lanes** at `extract-only`, over the art that actually
   decodes — the in-park textures (about 80% of each of the 87 ballpark
   archives) and the menu widget banks plus the 396 direct-colour team logos —
   each producing PNG through `ea_shps.decode_rgba` and refusing `0x0E` by
   name. **Not** a uniform lane, not a portrait lane and not a face lane:
   those surfaces are 100% `0x0E`, and a page that offers an export button
   which refuses every single item is worse than a page that says why.
4. **One audio export lane** at `extract-only` over the EA-XA streams, reusing
   `ea_schl` unchanged, with MicroTalk listed and refused.
5. **Page notes on the other pages**, each one sentence saying what was
   measured and why the page shows what it shows — not "coming soon". Three of
   them say the same thing and should say it in the same words: the art is
   there, it is catalogued, and its codec is not decoded (§6.1).
6. `ea_big.py` and `ea_shps.py` joining the release allowlist and the runtime
   checker's module list, which is where they belong once a shipped module
   imports them. **They are deliberately in neither today**, because nothing
   ships them yet.

No writer, and no `runtime-proved` anything: the disc has never been rebuilt
and never been booted from a rebuild by this project.

---

## 9. Verifying this document

Every number above came from `ea_big` and `ea_shps` run against the retail ISO
on the test rig, read-only, in a single process, with nothing written outside
a scratch directory and no game bytes brought back. The archive counts,
entry counts, RefPack count and `SHPS` count agree with the owner's
independent disc mapper [S]; the boot-ELF digest was recomputed and matches.

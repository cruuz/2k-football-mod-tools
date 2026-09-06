# NCAA Football 09 (PlayStation 2) — what the module does today

The third game on the Game Studio shell. Like Madden 09 it ships no window of
its own: `studio_window` points at the core shell, which draws the same fourteen
pages every studio has. A lane reaches its page by being a lane; a page with no
lane says why in one sentence.

This document is the honest inventory: what each page does, what is measured,
what is merely sourced, what is assumed, and — at the end — the list of things
this module deliberately does **not** claim.

**Six registry rows fill five of the fourteen pages** (§3): four inspect, two
export, **none writes**. Nothing has been booted, and nothing on this disc has
been rebuilt by this module. §11 answers the seven-point shipping standard for
the module as it stands.

**Evidence tags, on every load-bearing claim.**
**[M]** measured — a read-only command was run against a disc this box holds and
the number is quoted. **[S]** sourced — someone else's finding, cited.
**[A]** assumed — inference, not verified; treat it as a question.

**Retail-free.** Everything below is a name, an offset, a length, a count or a
digest. No member payload, no decoded pixel and no string from the game appears
here or in the code.

---

## 1. The disc

One image is recognised [M]:

| | retail |
|---|---|
| serial | `SLUS-21752` |
| boot file | `SLUS_217.52` |
| boot ELF SHA-256 | `dc1b3089…9c1f71ee` (7,294,796 bytes) |
| PCSX2 CRC | `B0157E6C` |
| image SHA-256 | `e15ba4d0…b9fb7de8` |
| image bytes | 2,175,041,536 |
| files / directories | 166 / 9 |
| `/DATA` files | 90 |

There is no community rebuild of this disc in this project's reach, so unlike
Madden 09 there is one digest, not two. A disc booting another serial is refused
with one sentence naming what was expected. An NCAA Football 09 re-cut whose ELF
matches neither digest is **not** refused: it is reported as `unknown edition`,
catalogued like any other, and nothing about it is claimed. Every lane here is
read-only, so nothing is risked by listing it.

Identity comes from the shared `Ps2DiscIdentifier` (ISO9660 volume +
`SYSTEM.CNF` + boot ELF) with the edition layered on in `disc_identity.py`.

---

## 2. The containers, and the rung everything stands on

Every large `/DATA/*.DAT` is an EA `TERF` container — the same format Madden 09
ships, documented in [`EA_TERF_FORMAT.md`](EA_TERF_FORMAT.md), read by the
**shared** `mod_editor/games/_formats/ea_terf.py`. This module contributes the
game-specific half only: which files to walk, how much of one it will hold, and
how to recover a container the disc's own directory record understates.

Measured on this disc [M]:

```
85 TERF containers · 30,391 members
chains   TERF->DIR1->DATA 49 · TERF->DIR1->COMP->DATA 35 · TERF->HSH1->DIR1->DATA 1
aligns   4 ×28 · 16 ×27 · 64 ×20 · 2048 ×10
codecs   stored 22,801 · LZH1 7,157 · RLE1 433
formats  SCHl 8,021 · unclassified 7,058 · MMAP 6,978 · SMF 3,301 · empty 1,416
         TEXT 1,247 · BNKl 728 · DMF 603 · TDB 581 · TERF 411 · FNTS 17 · MPCh 12
```

**85 of 85 containers parse and 30,391 of 30,391 members decode**, with zero
layout violations [M]. That total is two passes: 21,617 members classified by
holding 83 containers whole, and the remaining 8,774 in `SPCHDATA.DAT` (7,614)
and `SOUNDDAT.DAT` (1,160) classified by walking their directories in place,
because neither fits in memory. Every member on the disc is accounted for by one
pass or the other. That is the rung; every lane below stands on it.

### 2.1 Container size limit

The module reads a container up to **144 MB** and lists anything larger with its
size, unread. The limit is chosen, not inherited: `UNIFORM.DAT` is 127,942,528
bytes and is the kit art the Uniforms page is about, so it must be inside. The
four left outside are `STADIUMS.DAT` (197 MB), `MOVIEDAT.DAT` (333 MB),
`SOUNDDAT.DAT` (539 MB) and `SPCHDATA.DAT` (631 MB) [M]. The audio lane reaches
the two it needs through a **memory map** instead, which costs no copy at all —
so "listed unread" is a state the catalogue names for four containers and a gap
for none.

### 2.2 The three preload caches

NCAA 09 ships **three** `QL01` caches where Madden 09 ships two: `FE.QKL`
(10,567,452 bytes), `GAME.QKL` (16,364,860) and `PL.QKL` (3,129,350). Read by
this module's own parser: **564 copy entries** — 81 container directories and
483 members — naming 36, 27 and 9 containers [M]. Each is a byte copy of
something already on the disc, so **any future writer that changes a member's
stored size or codec moves a directory these caches carry**, and a stale cache
hands the game the wrong offsets. No lane here writes, so none has to solve it
yet; the fact is recorded so nobody writes one that does not.

---

## 3. The pages

The shell draws the same fourteen pages for every game, in its own order
(`PAGE_ORDER`, `mod_editor/games/contract.py`). NCAA 09 fills **five** of them
with **six registry rows**; eight state a measured reason instead (§4);
**Build & Share** is the shell's own page.

| § | page | row(s), all prefixed `ncaa09ps2.` | rung |
|---|---|---|---|
| 3.1 | Uniforms & Equipment | `uniforms.texture_census` | `read-only-mapped` |
| 3.2 | Names, Numbers & Faces | `players.league_databases` | `read-only-mapped` |
| 3.3 | Text & Team Identity | — | §4 |
| 3.4 | Field Art & Create-Team Art | — | §4 |
| 3.5 | Stadiums | — | §4 |
| 3.6 | Presentation | — | §4 |
| 3.7 | Menus & UI | `menus.text_members` | `read-only-mapped` |
| 3.8 | The Crib | — | §4 |
| 3.9 | Audio | `audio.streams` · `audio.banks` | `extract-only` · `extract-only` |
| 3.10 | Gameplay | — | §4 |
| 3.11 | Playbooks & Plays | — | §4 (the databases are on 3.2) |
| 3.12 | All Textures | `textures.container_inventory` | `read-only-mapped` |
| 3.13 | Saves | — | §4 |
| 3.14 | Build & Share | — | the shell's own |

### 3.1 Uniforms & Equipment — `uniforms.texture_census`

**`read-only-mapped`.** Reads the `MMAP` wrapper header of every kit, equipment
and face texture through the shared `ea_terf.parse_mmap_header`: version, header
size, declared payload size and the dimensions that follow the header.

Measured on the retail disc [M]: **2,566 `MMAP` members, 0 refused**, in
**2.7 s** —

| container | members | what it is |
|---|---:|---|
| `UNIFORM.DAT` | 1,200 | kit textures, `LZH1`-packed |
| `PLADATA.DAT` | 888 | player equipment, `LZH1` |
| `UIS_GEAR.DAT` | 396 | gear icons, stored |
| `PLYRFACE.DAT` | 64 | player faces, stored |
| `COACFACE.DAT` | 18 | coach faces, stored |

Dimensions: 256×256 ×762, 64×64 ×675, 128×128 ×480, 128×64 ×326, 256×128 ×79,
32×32 ×37, 1483×32 ×1 [M]. 206 members declare a 0-byte header and 1×3
dimensions — a shape the wrapper parser reads and the texture parser does not,
the same 0x400-format entries the owner's disc map records [M].

Only the first **64 bytes** of a member are unpacked, because that is every byte
the wrapper parser reads. Unpacking `UNIFORM.DAT`'s 1,200 `LZH1` members in full
took **7 m 22 s**; at the 64-byte window the whole census takes 2.7 s [M]. The
completeness is identical; only the cost changed.

**There is no kit *table* to pair this with.** Every uniform-shaped table on the
disc — `CTTB` (104 fields), `CTCD` (45), `CTUN` (28), `USTG`, `USLG`, `USLE` —
has **0 rows**, because they are the create-a-school tables and nobody has
created one; Madden 09 by contrast ships `UNIF` with 270 rows [M]. A school's kit
here **is** these textures and nothing else, which is why this page has an art
row and no database row.

**It is not an exporter, and does not pretend to be.** A pixel decoder for
`MMAP` exists in this repository — but inside the Madden 09 package, and
`mod_editor/games/_formats/__init__.py` is explicit that *a game imports a format
package; it never imports another game*. So the row is `read-only-mapped` and
its refusal says exactly that. Run from a scratch harness outside the module,
sampling 40 `MMAP` members per container, that decoder draws **1,019 of 1,063**
and refuses **44** [M], in three groups it names: 23 palette-only entries that
carry an alternate CLUT for another image and have no pixels of their own, 19
that declare no palette and so are not indexed textures, and 2 whose surface does
not satisfy the stride rule. That is a measurement of the decoder, not a
capability of this module.

**What lifts it:** move `mmap_art.py` into `_formats`. That is a shared-file
change, not a change to this module, and it turns this row into an exporter
unchanged.

### 3.2 Names, Numbers & Faces — `players.league_databases`

**`read-only-mapped`.** Every EA TDB database on the disc, table by table, with
each field's name, type, bit width and bit offset, and the four CRC-32/MPEG-2
slots EA stores in each one verified against the file's own bytes.

Measured on the retail disc [M], in **7.5 s**:

```
582 databases   (433 in LEAGUE.DAT, 137 in GAMEDATA.DAT,
                 11 in TEMPLATE.DAT, 1 bare STRMDATA.DB)
580 parse · 2 refused · 3,702 tables · 71,772 field definitions
11 distinct schema shapes
8,564 of 8,564 checksum slots hold the value they recompute to
```

`LEAGUE.DAT` is the surprise, and it is the reason this row is on the roster
page: **432 of its 433 databases are per-team rosters**, each holding exactly a
`PLAY` and a `DCHT` table — **24,717 player rows** in 30,240 slots and 24,856
depth-chart rows, 43 to 69 players per team [M].

**The catalogue carries field names, not field values.** A field name is the
schema and is identical on every disc; a record's contents are the user's game
data. A test asserts the point by searching the serialised catalogue for the
synthetic fixture's own string values and failing if it finds one.

**A refused database is recorded, not dropped.** Two of the 582 declare a field
type the shared reader does not name, and a catalogue that quietly omitted them
would read as if they were not there. Both appear in the document with the
reader's own sentence (§5).

**Why there is no writer, measured rather than pending.** This disc's `PLAY`
table has 86 fields to Madden 09's 110 and shares 37 names with it; it carries
**neither `PFNA` nor `PLNA`**, because NCAA's players have no names, and no
`PAGE` either. Its `POVR` and twenty attribute fields are **5 bits** wide where
Madden's are 7, and a five-bit field holds 0..31 — so the scale a rating is on
is not established and no spinner may claim one.
[`NCAA09_PS2_SCHEMA.md`](NCAA09_PS2_SCHEMA.md) is the field-by-field census.

### 3.3 Text & Team Identity — no lane

The 432 schools are in `LEAGUE.DAT`'s `TEAM`: `TDNA` (22 bytes), `TMNA` (18) and
`TSNA` (7) hold the names, and 29 of its 74 field names are shared with Madden
09's `TEAM` [M]. Madden's identity writer also writes `TLNA`, `TMNC` and six
colour bytes, and **none of those eight fields exists on this disc** [M]. A
64-row `PACL` palette (`CRED`/`CGRN`/`CBLU` per `PCID`) is here, and the
create-a-school `CTCD`/`CTUN` tables are here with 0 rows; which `TEAM` field
selects a school's palette entry is not established [A]. Conferences (`CONF`, 25
rows, `CNAM`) and divisions (`DIVI`, 10 rows, `DNAM`) are catalogued by §3.2's
lane. The page states this rather than offering a control with nothing behind it.

### 3.4 Field Art & Create-Team Art — no lane

`STADATA.DAT` holds 1,195 `MMAP` members and `UIS_TMLO.DAT` 399, plus 45 `SMF`
geometry members [M]. Blocked on exactly one thing, and it is §3.1's: the `MMAP`
pixel decoder is not in `_formats`.

### 3.5 Stadiums — no lane

The disc ships a real stadium **table** — `LEAGUE.DAT`'s `STAD`, 242 rows of 56
fields including `SNAM` (30 bytes), `STNN`, `SCIT`, `SSTA` and a 17-bit `SCAP`
capacity [M] — which Madden 09 does not have outside its templates; §3.2's lane
catalogues it. The **art** is another matter: `STADIUMS.DAT`'s 2,914 members are
1,880 `SMF` and 1,034 empty, and `STADATA.DAT` adds 45 `SMF` and 4 `DMF` [M].
**No `SMF` or `DMF` reader exists anywhere in this repository**, so the geometry
is listed by format and left alone; the textures wait on §3.1's decoder move.

### 3.6 Presentation — no lane

`FANDATA.DAT` 244 `MMAP`, `MSCTDATA.DAT` 240 `MMAP` and 400 `DMF`,
`LOADDATA.DAT` 46 `MMAP` (30 of them 854×480), `MOVIEDAT.DAT` 12 `MPCh` [M].
Three separate blockers: the `MMAP` decoder move, a `DMF` model reader nobody has
written, and a movie decoder this repository does not have and does not claim.

### 3.7 Menus & UI — `menus.text_members`

**`read-only-mapped`.** Every `TEXT` string bank, measured: how many
NUL-terminated slots, how many characters, how much room past the strings that
are there now, and whether the member ends in a terminator.

Measured on the retail disc [M], in **0.6 s**: **1,247 `TEXT` members, 1,247
slots, 241,787 characters** — `EXAMS.DAT` 1,238, `JERSEY.DAT` 7, `OSDKSTRN.DAT`
1, `GAMEDATA.DAT` 1.

Three measurements about their shape, and all three matter to a writer [M]:

* **every one of the 1,247 members holds exactly one run** — the slot histogram
  is `{1: 1247}`, so no member on this disc is a multi-string bank;
* **not one ends in a terminator**, where Madden 09's banks are a mix;
* **there is no padding anywhere** — 0 spare bytes across all 1,247.

So a same-allocation writer for this disc has **no slack to work with at all**: a
replacement must be exactly the length it replaces, or shorter and pay for the
terminator it introduces. Runs go from 15 to 50,519 bytes.

**The strings are never stored here.** The catalogue carries counts and lengths;
a string reaches the user only through `preview`, read off their own image at the
moment they ask for it. A test asserts the synthetic fixture's own lines are
absent from the serialised document.

The slot rule is the one that makes a future edit reversible: a slot's
*allocation* is the room it has, running to the next slot less the terminator, so
a bank a previous edit shortened still shows the room its padding occupies. That
is implemented and tested; the writer that would use it is not built, because it
needs a container writer and the three caches kept in step (§2.2).

`FONTS.DAT` and `UIS_FONT.DAT` hold 17 `FNTS` fonts [M]; no font decoder exists
here.

**The rest of this page is art, and has no lane.** The menu textures live across
**51 further containers** [M] — the 31 `UIS_*.DAT` (`UIS_BGSP.DAT` 689 `MMAP`,
`UIS_MCFL.DAT` 409, `UIS_TMLO.DAT` 399, `UIS_STAD.DAT` 244 and 27 more) and the
20 `CAFE*.DAT`, whose members are nested `TERF` archives of Apt screens and
textures — and they wait on the same `MMAP` decoder move as §3.1. The container
inventory (§3.12) lists every one of them with its members and formats today.

### 3.8 The Crib — no lane

An ESPN NFL 2K5 feature and not an NCAA Football concept. Empty on purpose.

### 3.9 Audio — `audio.streams` and `audio.banks`

Both **`extract-only`**: a WAV comes out, nothing goes back in.

Measured on the retail disc [M]:

| | streams | banks |
|---|---:|---:|
| members | 8,021 `SCHl` | 728 `BNKl` |
| open | 8,021 headers | 728 of 728 |
| decode here | **412** | 1,213 sounds, **753** with a rate |
| codec | EA-XA ADPCM ×412, MicroTalk ×7,609 | PlayStation ADPCM |
| platform tag | `PT` ×412, `GSTR` ×7,609 | — |

`SPCHDATA.DAT` carries 7,609 streams and **every one is MicroTalk** — EA's speech
codec, for which no decoder exists in this repository or in ffmpeg [M/S]. They
are listed with their rate, channels and length and their audio is refused by
name rather than guessed at. The 412 that decode are `SOUNDDAT.DAT`'s 408 and
`FESNDDAT.DAT`'s 4. Whole-disc catalogue: **7.2 s** [M].

Both containers are past the 144 MB read limit, so the lane **memory-maps the
image** and walks the `TERF` directory in place: no copy of a 631 MB container is
ever made. A raw-CD image is refused by name, because the map needs the 2048-byte
sector layout every PlayStation 2 DVD uses.

**What the export writes and what checks it.** `build` writes a NEW manifest and
a NEW folder of WAVs beside it, neither of which may already exist, and refuses a
destination that is the source. `verify` **re-decodes every exported file from
the user's own disc by key** — not through the catalogue that produced the
receipt — and fails on a tampered WAV, on an undeclared file in the export
folder, and on a missing one. All three cases have a test.

**What is not claimed:** a bank sound that declares no rate is refused rather
than written at a rate nobody measured (460 of the 1,213). No stream and no bank
sound has been replaced, on this disc or any other.

### 3.10 Gameplay — no lane

The boot executable is `SLUS_217.52`, 7,294,796 bytes, sha256 `dc1b3089…`,
PCSX2 CRC `B0157E6C` [M]. **No patch site on it has been located by this
project**, and every site is per-title research: nothing found in Madden 09's
`SLUS_217.70` applies here. The page carries no lane rather than a scaffold with
nothing in it.

### 3.11 Playbooks & Plays — no lane, and the closest near-miss on the disc

`GAMEDATA.DAT` holds 137 databases at members 4–140: one shared play library and
136 playbooks, all one schema shape [M]. **Their nineteen tables are name-for-name
identical to Madden 09's nineteen** — the closest the two discs come anywhere.

What stops the Madden playbook writer porting is one field: Madden's `PBPL`
carries a play `name` and this one's does not, so the play names live in `PLYL`
(192-bit strings) instead, and five widths shift [M]. **13,817 name-bearing rows**
are on the disc: `PLYL` 4,322, `PBST` 3,266, `PBFM` 2,356, `SGF\x00` 2,086,
`SPKF` 1,510, `SETL` 236, `FORM` 41. 2,301 of the 2,603 tables are packed exactly
full, so a rename is possible and an insertion is not — the same ceiling Madden's
books have.

The databases themselves are catalogued by §3.2's lane, which is why this page
has a note and not a duplicate row.

### 3.12 All Textures — `textures.container_inventory`

**`read-only-mapped`.** Every `/DATA` file: the chunk chain, the alignment, each
member's offset, stored size, codec and unpacked size, and — after decompression,
because a packed member's stored magic means nothing — what format its bytes
carry.

Measured on the retail disc [M], in **6.5 s**: **90 `/DATA` files, 81 containers
read, 4 listed unread, 18,691 members** in the containers read; codecs stored
12,981, `LZH1` 5,277, `RLE1` 433 across those. The first 256 members of each
container are decompressed to classify them, and every row says how many it
sampled, so nobody reads a histogram as the whole container. The document's
whole-disc totals (30,391 members) come from §2.

### 3.13 Saves — no lane

An NCAA Football 09 memory-card save is a different source; this studio works off
the disc. This is also where the **"Send to Madden" draft class** lives: it is a
save the game writes at runtime, and no table on this disc holds one
([`NCAA09_PS2_SCHEMA.md`](NCAA09_PS2_SCHEMA.md) §9).

### 3.14 Build & Share — the shell's own page.

---

## 4. Pages that state a reason instead of a lane

`game.json` carries **nine** page notes, each a sentence the shell draws under
its own [M]. Eight are on pages with no lane — `identity`, `field_art`,
`stadiums`, `presentation`, `crib`, `gameplay`, `playbooks`, `saves` — and the
ninth, `rosters`, sits under a page that *has* a lane and says why that lane does
not write. Every one names a **measured** reason: a format with no reader in this
repository, a concept the game does not have, or a field that is not on the disc.
"Not built yet" appears nowhere.

---

## 5. What the readers refused, grouped by sentence

Two refusals in two groups, both from `ea_tdb.parse_tdb`, both recorded in the
database lane's own document [M]:

| reader | count | sentence | where |
|---|---:|---|---|
| `ea_tdb.parse_tdb` | 1 | *field ASNA of table ANIN covers bits 0..400 of a record that is 8 byte(s) long; the field directory is being read at the wrong offset or the file is damaged.* | `/DATA/STRMDATA.DB` |
| `ea_tdb.parse_tdb` | 1 | *field SPFN of table RCFN covers bits 0..80 of a record that is 8 byte(s) long; …* | `/DATA/TEMPLATE.DAT:3` |

Both are the same cause: **TDB field types 13 and 14**, which the shared reader
does not name — 18 type-13 fields and 1 type-14 in `STRMDATA.DB`, 2 type-13 in
`TEMPLATE.DAT:3`, every one declaring a width larger than its own record at a
bit offset that is a multiple of 32 [M]. `NCAA09_PS2_SCHEMA.md` §7 has the
evidence and the reading. It matters more than two databases: `RCFN` (8,191 rows)
and `RCLN` (6,915) are a first-name and last-name pool, which makes them the one
place on this disc where player names live.

No other reader refused anything: 0 of 85 containers, 0 of 30,391 members, 0 of
2,566 `MMAP` headers, 0 of 8,021 `SCHl` headers, 0 of 728 banks [M].

---

## 6. What is measured, in one table

| claim | number | how |
|---|---|---|
| containers parse | 85 / 85 | `ea_terf.parse_terf` |
| members decode | 30,391 / 30,391 | `ea_terf.decompress_member` |
| databases parse | 580 / 582 | `ea_tdb.parse_tdb` |
| checksum slots agree | 8,564 / 8,564 | `ea_tdb.crc_sites` |
| tables / field definitions | 3,702 / 71,772 | the database lane |
| distinct schema shapes | 11 | the database lane |
| per-team rosters | 432, 24,717 player rows | the database lane |
| playbook databases | 137, 13,817 name rows | the database lane |
| `MMAP` headers read | 2,566 / 2,566 | the texture lane |
| `TEXT` members measured | 1,247, 241,787 bytes | the text lane |
| `SCHl` streams | 8,021, 412 decodable | the audio lane |
| `BNKl` banks / sounds | 728 / 1,213, 753 with a rate | the audio lane |
| preload copy entries | 564 across three caches | `containers.parse_preload_cache` |
| catalogue wall time | inventory 6.5 s · databases 7.5 s · textures 2.7 s · text 0.6 s · audio 7.2 s | the five lanes |

---

## 6a. Wall time — cataloguing this disc

Every number in this document came from a read-only run against the 2.18 GB
image on this box. What each cost [M]:

| what | time |
|---|---|
| `inventory_lane` — 90 `/DATA` files, 81 containers, 18,691 members classified | **6.5 s** |
| `database_lane` — 582 databases, 3,702 tables, 71,772 fields, 8,564 checksums | **7.5 s** |
| `texture_lane` — 2,566 `MMAP` wrapper headers | **2.7 s** |
| `text_lane` — 1,247 `TEXT` banks measured | **0.6 s** |
| `audio_lane` — 8,021 stream headers and 728 banks, memory-mapped | **7.2 s** |
| **the five lanes, end to end** | **≈ 25 s** |

And the scratch measurements behind §5 and `NCAA09_PS2_SCHEMA.md`, which are not
part of the module [M]:

| what | time |
|---|---|
| whole-disc TDB schema census (this disc) | 7.2 s |
| the same census on Madden 09, as the control | 23.6 s |
| the same census on NCAA Football 2004 | 11.5 s |
| whole-disc member classification + CRC pass | 79.4 s |
| streaming codec census over the four oversized containers (1.5 GB) | 160.2 s |

One number is worth keeping in view: unpacking `UNIFORM.DAT`'s 1,200 `LZH1`
members **in full** took **7 m 22 s**, against 2.7 s for the whole texture census
at a 64-byte window [M]. Any future art lane pays the first number, not the
second, and should say so.

---

## 7. What this module does not claim

1. **Nothing has been booted.** No image built from this disc exists, because no
   lane here writes one.
2. **No pixel is decoded.** The texture row reads headers. It says so in its own
   refusal.
3. **No rating scale is known.** `PLAY`'s ratings are 5 bits; what 0..31 means on
   screen is unestablished, and no control offers a number.
4. **No colour is editable**, because the `TEAM` table has no colour field and the
   `TEAM` → `PACL` link is unproved.
5. **Two databases are unread**, and the field type behind them is described, not
   decoded.
6. **`SMF`, `DMF`, `MPCh` and `FNTS` are named and never opened** — 3,301, 603,
   12 and 17 members [M]. No reader for any of them exists in this repository.
7. **MicroTalk is refused, not approximated** — 7,609 streams.
8. **NCAA Football 06 is not on this box**, so the on-disc `PLAY` record could not
   be diffed against the NCAA-06 draft-class format the owner's research decoded;
   that research is cited as [S] and used as a reading of field meanings, not as a
   measurement.

---

## 8. What the writers need

Every writer this module could gain is a **shared** writer that already exists
for Madden 09, waiting on a schema table or one missing piece.

| writer | what it needs here |
|---|---|
| **TDB record writer** (`ea_tdb.write_records`, `recompute_crcs`) | exists and is shared. It needs a *field map* for this disc: which `PLAY` fields an editor offers, given there is no name and the ratings are 5 bits. The four CRCs are already proved on this disc's own bytes, 8,564 of 8,564, so the check has teeth before the writer exists. |
| **Container member rewrite** (`ea_terf.rewrite_member`) | exists and is shared. It needs the **three** `QL01` caches kept in step (§2.2) and the ISO writer pointed at this disc. `LEAGUE.DAT` is `RLE1`, whose encoder `ea_terf` already has. |
| **Text slot writer** | the format is identical to Madden 09's and this module already implements the slot-allocation rule and tests it. It needs the container writer above and nothing else. |
| **Playbook name writer** | needs a new field map, not new code: 19 of 19 tables match by name, and the play name is in `PLYL` rather than `PBPL`. |
| **`MMAP` art writer** | needs `mmap_art.py` moved from the Madden package into `_formats`, then the `LZH1` encoder (which now exists) for `UNIFORM.DAT` and `PLADATA.DAT`; `UIS_GEAR.DAT`, `PLYRFACE.DAT` and `COACFACE.DAT` store their members uncompressed and need no encoder at all. |
| **Audio stream / bank writer** | the EA-XA and PS-ADPCM encoders exist and are shared. Needs the container writer and the caches; MicroTalk stays out of reach. |
| **Identity writer** | has **no target on this disc**: `TLNA`, `TMNC` and all six colour fields are absent. It needs the `TEAM` → `PACL` link found first, and then it is a *different* writer, not a port. |
| **Executable patches** | needs translations. None is mapped for `SLUS_217.52`. |

---

## 8a. Two things a third game broke, and what was done

Madden 09's document has a section like this because the second game found four
one-game assumptions. The third found two more, and both are the same defect:
**a test that enumerates the games hosted on the day it was written.**

### 8a.1 The chooser test listed the studios

`tests/mod_editor/test_games_chooser.py` asserted the chooser table equals
`["PS2 Madden 09 Studio", "PS2 NFL 2K5 Studio"]` exactly. It is a **frozen** file,
so the second game moved it from one row to two through the version procedure —
and the third hit the identical wall. `MADDEN09_PS2_MODULE.md` §8.1 had already
named the right fix ("assert the PS2 row is *present* rather than sole") and left
it undone.

**Done now**: the test asserts one row per discovered game, the two known PS2 rows
present, and the rows in the order `ChooserRow.sort_key` defines. A fourth game is
no longer a frozen-file edit. The contract's behaviour did not change, so it is a
note under 1.0 (unreleased) and a `pins --write`, committed alone as the procedure
requires.

### 8a.2 The 2K3/2K4 boundary test listed the `GameId` enum

`tests/mod_editor/test_nfl2k3_2k4_compatibility_boundary.py` asserted the whole
enum equals four ids, in a test whose subject is that `nfl2k3` and `nfl2k4` are
**not** in it. Not frozen, but the same mistake: every new module had to edit a
file that had nothing to say about it.

**Done now**: it asserts the two ids are absent and the three the boundary
protects are present, and says nothing about the rest.

Neither is a change to the shell, the contract or any game's behaviour. Both are
listed here because they are edits outside this module's directory, which a game
PR owes an account of.

### 8a.3 Every file outside this module that changed

Twenty-one of them, and **all but four are `tools/registry_add_rows.py`'s own
mechanical output** — the registry, its two schemas, the `GameId` enum and its
loader, the coverage table, the release allowlist, the two runtime gates and the
thirteen count pins:

```
mod_editor/capabilities/registry.v1.json         registry.schema.json
mod_editor/capabilities/validate_registry.py     mod_editor/core/capabilities.py
mod_editor/core/model.py                         mod_editor/project.schema.json
packaging/release-allowlist.txt                  packaging/check_2k5_mod_studio_runtime.py
packaging/check_apf2k8_mod_studio_runtime.py     tools/validate_all_mod_editor_capabilities.py
tests/mod_editor/test_phase1_packaging.py        tests/mod_editor/test_apf_studio_installer.py
APF2K8-README.md   STATUS.md   docs/mod_editor/APF2K8_STATUS.md
docs/mod_editor/2k5_mod_studio_getting_started.md
```

The four that were **not** the tool's output, each with its reason:

| file | why |
|---|---|
| `mod_editor/core/providers.py` | the unified provider pins `mod_editor/core/model.py`, and the new `GameId` member changed that file. The same step the Madden 09 module needed (`ea25375`). |
| `tests/mod_editor/test_games_chooser.py` | §8a.1 |
| `mod_editor/games/CONTRACT_PINS.json`, `CONTRACT_CHANGELOG.md` | the procedure that goes with it |
| `tests/mod_editor/test_nfl2k3_2k4_compatibility_boundary.py` | §8a.2 |

Nothing in `mod_editor/gui/studio_qt.py` or `mod_editor/__main__.py` changed, and
no `_formats` reader changed: **the shared readers opened this disc unmodified**,
which is the whole claim of §2.

---

## 9. Where the code is

```
mod_editor/games/ncaa09_ps2/
  __init__.py        GAME, IDENTITY, the six lanes, the studio window
  containers.py      disc access, container reports, the QL01 caches,
                     and every synthetic source CI proves a lane on
  disc_identity.py   which image this is
  inventory_lane.py  §3.12
  database_lane.py   §3.2
  text_lane.py       §3.7
  texture_lane.py    §3.1
  audio_lane.py      §3.9, both rows, and the memory-mapped disc reader
tools/validate_ncaa09_ps2_{inventory,databases,text,textures,audio}.{sh,bat}
tests/mod_editor/test_ncaa09_ps2_module.py    the harness and the fragment check
tests/mod_editor/test_ncaa09_ps2_lanes.py     21 tests over the lanes
docs/product/measured/ncaa09_ps2/tdb-schema.json
```

Every lane runs without a window:

```
python3 -m mod_editor.games.ncaa09_ps2.inventory_lane --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.database_lane  --source "<your>.iso" --out schema.json
python3 -m mod_editor.games.ncaa09_ps2.text_lane      --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.texture_lane   --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.audio_lane     --source "<your>.iso"
```

and each takes `--selftest` instead, which runs it on a synthetic disc and needs
no game data at all.

---

## 10. The studio

`python -m mod_editor.games` lists **PS2 NCAA 09 Studio**, Ready, 6 lanes,
alongside the other two PS2 studios. The label is composed from `console` /
`game` / `year` in `game.json` and is typed nowhere.

Opened headless (`QT_QPA_PLATFORM=offscreen`), the window titled
`PS2 NCAA 09 Studio` draws **fourteen pages in the shell's order** [M]:

| # | page | widget | lane(s) |
|---:|---|---|---|
| 1 | Uniforms & Equipment | `LanePage` | `uniforms.texture_census` |
| 2 | Names, Numbers & Faces | `LanePage` | `players.league_databases` |
| 3 | Text & Team Identity | `UnavailablePanel` | — |
| 4 | Field Art & Create-Team Art | `UnavailablePanel` | — |
| 5 | Stadiums | `UnavailablePanel` | — |
| 6 | Presentation | `UnavailablePanel` | — |
| 7 | Menus & UI | `LanePage` | `menus.text_members` |
| 8 | The Crib | `UnavailablePanel` | — |
| 9 | Audio | two lane panels | `audio.streams`, `audio.banks` |
| 10 | Gameplay | `UnavailablePanel` | — |
| 11 | Playbooks & Plays | `UnavailablePanel` | — |
| 12 | All Textures | `LanePage` | `textures.container_inventory` |
| 13 | Saves | `UnavailablePanel` | — |
| 14 | Build & Share | `BuildPage` | the shell's own |

Six lanes on five pages, eight `UnavailablePanel`s each carrying their page's
sentence, and the shell's build page. No page is missing and none is silently
empty.

---

## 11. The shipping checklist

The seven-point standard from `ADDING_A_GAME_MODULE.md`, answered for this
module as it stands. **This module is not complete**, and these are the reasons.

1. **Every page has its answer** — **partly.** Five pages carry a lane; eight
   carry a measured sentence; one is the shell's. But `field_art`, `stadiums` and
   `presentation` — and the export half of `uniforms` — are all blocked on **one**
   thing, the `MMAP` decoder's location, which is a gap rather than a property of
   the disc. Said plainly: this module is at the rung its readers earn, and the
   reason the art pages are empty is a repository-layout fact, not an NCAA
   Football fact.
2. **Every writer is proved twice** — **not applicable: there are no writers.**
   The two export rows are proved offline by an independent verifier that
   re-decodes from the source and fails on tampering; neither writes to a disc.
3. **Art round-trips** — **no.** No pixel is decoded here. §3.1.
4. **Rosters, team data and text have writers with the four CRCs proved** —
   **half.** The CRCs are proved: 8,564 of 8,564 on the disc's own databases,
   before any write is offered, which is the order the standard asks for. The
   writers do not exist, and §3.2 says which fields are missing.
5. **Audio, stadiums, playbooks and gameplay patches at the rung their formats
   permit** — **audio yes** (`extract-only`; the codec that would lift it does
   not exist publicly). **Stadiums and playbooks no**: the geometry has no reader
   anywhere here, and the playbook writer needs a field map. **Gameplay no**: no
   patch site is located.
6. **Validators run in a shipped tree and on a real cmd.exe** — the five `.sh`
   validators run in a staged tree on Linux and print their PASS lines; the five
   `.bat` mirrors are written without parentheses inside `if` blocks and have
   **not been run on a real cmd.exe from here**.
7. **Nothing is claimed above its proof** — every row is `read-only-mapped` or
   `extract-only`, no row is hidden, and §7 is the list of what is not claimed.

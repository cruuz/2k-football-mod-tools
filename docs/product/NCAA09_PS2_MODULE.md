# NCAA Football 09 (PlayStation 2) — what the module does today

The third game on the Game Studio shell. Like Madden 09 it ships no window of
its own: `studio_window` points at the core shell, which draws the same fourteen
pages every studio has. A lane reaches its page by being a lane; a page with no
lane says why in one sentence.

This document is the honest inventory: what each page does, what is measured,
what is merely sourced, what is assumed, and — at the end — the list of things
this module deliberately does **not** claim.

**Fourteen registry rows fill twelve of the fourteen pages** (§3): **nine
write**, two export, three inspect. Every writer is proved offline twice — on a
synthetic disc in CI, and by hand on the retail image, with the numbers in §3a.
**Nothing has been booted**: no image built from this disc has been run in an
emulator or on hardware, and no row says otherwise. §11 answers the seven-point
shipping standard for the module as it stands.

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
| 3.1 | Uniforms & Equipment | `uniforms.texture_census` · `uniforms.disc_art_writer` | `extract-only` · **`offline-writer-proved`** |
| 3.2 | Names, Numbers & Faces | `players.league_databases` · `rosters.face_textures` | **`offline-writer-proved`** ×2 |
| 3.3 | Text & Team Identity | `identity.league_records` | **`offline-writer-proved`** |
| 3.4 | Field Art & Create-Team Art | `field_art.textures` | **`offline-writer-proved`** |
| 3.5 | Stadiums | `stadiums.textures` | **`offline-writer-proved`** |
| 3.6 | Presentation | `presentation.ui_textures` | **`offline-writer-proved`** |
| 3.7 | Menus & UI | `menus.text_members` | **`offline-writer-proved`** |
| 3.8 | The Crib | — | §4 |
| 3.9 | Audio | `audio.streams` · `audio.banks` | `extract-only` · `extract-only` |
| 3.10 | Gameplay | — | §4 |
| 3.11 | Playbooks & Plays | `playbooks.databases` | **`offline-writer-proved`** |
| 3.12 | All Textures | `textures.container_inventory` | `read-only-mapped` |
| 3.13 | Saves | `saves.draft_class` | `read-only-mapped` |
| 3.14 | Build & Share | — | the shell's own |

**Twelve of the fourteen pages carry a lane.** Two do not, and both reasons are
measured rather than pending: the Crib is an ESPN NFL 2K5 feature and not an
NCAA Football concept, and no patch site on `SLUS_217.52` has been located by
this project — none of the five `sltiu` immediates Madden 09's playbook-editor
patch uses is an address in this executable. A pnach writer with an empty
translation table would be a control that can only refuse, so the Gameplay page
carries the sentence instead.

### 3a. What each writer did on the retail disc

Every row marked `offline-writer-proved` was run twice: once by the conformance
harness on a synthetic disc built from the formats' own rules, and once **by
hand on the owner's own `SLUS-21752` image**.  The real-disc runs, with the
numbers the verifier produced [M].  Every destination was deleted afterwards
and the source's SHA-256 was re-checked and unchanged in each case.

| lane | what was written | s | declared | verifier |
|---|---|---:|---|---|
| `players.league_databases` | `LEAGUE.DAT#1:PLAY:0` — `PJEN` 77, `POVR` 29 | 113 | 2 ranges / 1,872,244 B | **PASS** · 2 values read back · 6 checksum slots correct · 4 cache copies still equal what they copy · 0 undeclared changed bytes |
| `identity.league_records` | `LEAGUE.DAT#0:TEAM:0` — `TDNA` | 76 | 4 ranges / 5,001,602 B | **PASS** · 1 value read back · 52 checksum slots · **4 cache copies rewritten and re-read** · 0 undeclared |
| `playbooks.databases` | `GAMEDATA.DAT#4:PLYL:0` — a play name | 97 | 4 ranges / 20,202,124 B | **PASS** · 1 value read back · 40 checksum slots · **18 cache copies** · 0 undeclared |
| `menus.text_members` | `EXAMS.DAT:0:0` — one string slot | 90 | 2 ranges / 182,744 B | **PASS** · 1 string read back · 1 bank re-read at its exact length · 0 undeclared |
| `rosters.face_textures` | `PLYRFACE.DAT:16:0`, 128×128, flipped | 147 | 4 ranges / 12,048,172 B | **PASS** · texture decodes from the new image as the PNG given · 79 untouched members byte-identical · **74 cache copies** re-read · 0 undeclared |
| `stadiums.textures` | `UIS_STAD.DAT:0:0`, 128×128, flipped | 87 | 4 ranges / 13,847,532 B | **PASS** · 244 untouched members byte-identical · 1 cache copy · 0 undeclared |
| `uniforms.disc_art_writer` | `UIS_GEAR.DAT:0:0`, 128×128, flipped | 514 | 2 ranges / 6,941,144 B | **PASS** · 395 untouched members byte-identical · **0 cache copies, because no cache names this container** · 0 undeclared |
| `field_art.textures` | `UIS_TMLO.DAT:0:0`, 128×128, flipped | 65 | 7 ranges / 18,117,900 B | **PASS** · 398 untouched members byte-identical · 9 cache copies · 0 undeclared · **the image grew** (below) |
| `presentation.ui_textures` | `FANDATA.DAT:12:0`, 128×128, flipped | 157 | 2 ranges / 5,906,696 B | **PASS** · 256 untouched members byte-identical · 1 cache copy · 0 undeclared |

**All nine writers were run**, one edit each. In eight of the nine the
destination came back **2,175,041,536 bytes — the
source's exact size** — and in all nine an adversarial flip of one byte
**outside** every declared range was refused by the verifier with the offset
named.

**The eighth is the one that grew, and that is the opt-in path working** [M].
The flipped `UIS_TMLO.DAT` logo re-packed under `LZH1` past the extent that
container owns, so the ISO writer relocated the file: the image went from
2,175,041,536 to **2,175,918,080 bytes**, 428 sectors longer, and the receipt
said so in seven declared ranges rather than two. Every art row declares
`fixed_allocation = False` for exactly this reason — "the image keeps its length
whenever the rebuilt container fits its extent, which is the ordinary case" is
what those rows promise, and it is not a guarantee. Six of the seven art and
record writes did keep the length; this one did not, and the number is in the
receipt rather than in a footnote.

**And the slowest one is worth its own line.** `uniforms.disc_art_writer` took
**514 s** against 65 to 147 for every other art row, because its catalogue walks
`UNIFORM.DAT` — 1,200 `LZH1` members carrying about 15,600 images. That is the
7 m 22 s figure §6a records for unpacking that container in full, and any lane
that offers its textures pays it.

**And one refusal, which is evidence too** [M].  The first identity trial asked
for a three-character `TSNA`.  That grew `LEAGUE.DAT` member 0's `RLE1`
encoding from 98,251 to 98,252 bytes, and that member is itself copied into
`PL.QKL` — a fixed slot.  The lane refused, by name and with both sizes:

> `LEAGUE.DAT member 0 is copied into PL.QKL and the rewrite changed its stored
> size from 98251 to 98252. A cached copy is a fixed slot, so this member cannot
> be rewritten at a larger size; nothing was written.`

That is the bound working on real bytes rather than on a fixture.  A name edit
moves the encoding by **-13 to +1 bytes** [M]; most shrink, and the one that
grew was stopped.

**What none of this is.** No rebuilt image has been booted. Nine writers wrote
bytes that a verifier importing none of them re-derived from the two files, and
whether NCAA Football 09 loads any of the results is not something this project
has found out.

### 3.1 Uniforms & Equipment — the kit art, exported and written back

Two rows, and they earn different rungs: `uniforms.texture_census`
(**`extract-only`**) decodes a kit texture to PNG, and
`uniforms.disc_art_writer` (**`offline-writer-proved`**) puts an edited one
back into a NEW image.

Measured on the retail disc [M]:

| container | members | what it is | preload caches |
|---|---:|---|---|
| `UNIFORM.DAT` | 1,200 `MMAP` | kit textures, `LZH1`, 127,942,528 bytes | directory ×4, 3 members |
| `PLADATA.DAT` | 888 `MMAP` | player equipment, `LZH1` | directory ×1, 8 members |
| `UIS_GEAR.DAT` | 396 `MMAP` | gear icons, stored | **named by none** |

`UIS_GEAR.DAT` is the cheapest thing on this disc to rewrite and the page says
so: no cached directory and no cached member moves with it.

**There is still no kit *table* to pair this with**, and that has not changed:
`CTTB` (104 fields), `CTCD` (45), `CTUN` (28), `USTG`, `USLG` and `USLE` all
have **0 rows**, because they are the create-a-school tables and nobody has
created one; Madden 09 by contrast ships `UNIF` with 270 rows [M]. **A school's
kit here *is* these textures and nothing else**, which is why this page has two
art rows and no database row.

**What changed since this page was a header census.** The `MMAP` pixel decoder
was inside the Madden 09 package, and `_formats/__init__.py` is explicit that a
game never imports another game — so the row could read a wrapper header and
nothing more. The decoder is now `mod_editor/games/_formats/mmap_art.py` and the
*lane* is `mod_editor/games/_lanes/terf_art.py`, which both games instantiate.
Nothing about this disc was in the way; the repository's layout was.

**One thing the move surfaced.** A flat target cap spent on the first container
listed leaves the last one unreachable: `UNIFORM.DAT`'s 1,200 members carry
about 15,600 images between them, so 4,000 targets never reached
`UIS_GEAR.DAT` — the one container a user should reach first. The base now
takes a per-container share and this row sets it to 1,500 [M].

**Every replacement identity here is derived and none is confirmed.** No PCSX2
texture dump has been paired with `SLUS-21752`. `derive_texture_names` computes
the GS `TEX0` and CLUT hashes from the texture's own bytes, and the page says
which kind of name it is showing. **No pack built from these names has been
loaded in an emulator.**

### 3.2 Names, Numbers & Faces — the 432 rosters, edited

Two rows: `players.league_databases` (**`offline-writer-proved`**) and
`rosters.face_textures` (**`offline-writer-proved`**).

The catalogue half is unchanged and still the widest thing this module does
[M], in **7.5 s**:

```
582 databases   (433 in LEAGUE.DAT, 137 in GAMEDATA.DAT,
                 11 in TEMPLATE.DAT, 1 bare STRMDATA.DB)
580 parse · 2 refused · 3,702 tables · 71,772 field definitions
8,564 of 8,564 checksum slots hold the value they recompute to
```

**What the writer edits.** `LEAGUE.DAT` members 1..432 — the per-team rosters,
**24,717 player rows** in 30,240 slots and 24,856 depth-chart rows [M]. Per
`PLAY` row: the squad number, the position id, the college class, the redshirt
flag, height, weight and the twenty attribute fields; per `DCHT` row, which
player fills a slot and how deep.

**What it will never offer, and why that is a measurement.** This `PLAY` table
carries **neither `PFNA` nor `PLNA`** — NCAA Football 09's players have no
names, which you can read straight off the field directory — and no `PAGE`
either, because a college player has a **class**. So the editor offers `PYER`
(3 bits) and `PRSD` (2 bits) where Madden's offers an age, and it draws no name
box at all. A test asserts the absence rather than trusting it.

**The rating scale, which used to be an open question, is settled** [M].
`POVR` and the twenty attributes are five bits. 3,295 records read off 62 of the
432 rosters find **every value 0..31 in use, with 536 of them (16%) on 31** —
the shape of a scale that saturates at its ceiling. The spinner's bound is
therefore **31**, the field's own, and no control claims a 0–99 number. What the
game *draws* from those five bits is still not established, and the two facts
are kept apart. [`NCAA09_PS2_SCHEMA.md`](NCAA09_PS2_SCHEMA.md) §2 is the census.

**Why the write is bounded.** A TDB field owns a fixed run of bits in a
fixed-stride record, so the database keeps its length. `LEAGUE.DAT`'s members
are `RLE1`, so the *stored* size could move — and measured on the retail disc it
does not: a `PLAY` edit in each of members 1, 5, 100 and 432 re-packs to
**exactly** the byte count EA shipped, so the container's directory never moves
and the two copies of it in `PL.QKL` stay valid [M]. The lane does not rely on
that; it prices the re-pack first and rewrites every cache copy an edit
disturbs.

**The face art** is `PLYRFACE.DAT` (80 members, 64 with an `MMAP` header) and
`COACFACE.DAT` (18) [M]. Which player a face belongs to is not established and
**could not be from this disc alone**: there is no name in `PLAY` to join it to.
The coaches *do* have names — `COCH.CLFN` and `COCH.CLLN` — but nothing joins a
coach row to a face member either, and the page says so.

### 3.3 Text & Team Identity — `identity.league_records`

**`offline-writer-proved`.** One database — `LEAGUE.DAT` member 0 — and the
names in five of its tables [M]:

| table | rows | what this row writes |
|---|---:|---|
| `TEAM` | 432 | `TDNA` (22 bytes), `TMNA` (18), `TSNA` (7) |
| `CONF` | 25 | `CNAM` (20) |
| `DIVI` | 10 | `DNAM` (20) |
| `STAD` | 242 | `SNAM` (30), `STNN` (18), `SCIT` (21), `SSTA` (15), `SCAP` (17-bit) |
| `COCH` | 315 | `CLFN` (10), `CLLN` (13) |

The coaches have names on this disc even though the players do not.

**There is no colour control, and the reason is on the page.** Madden 09's
identity writer writes `TDNA`/`TLNA`/`TSNA`/`TMNC` and six colour bytes.
**`TLNA`, `TMNC` and all six colour fields are absent here** [M]. A 64-row
`PACL` palette (`CRED`/`CGRN`/`CBLU` per `PCID`) *is* on the disc and the
catalogue reports it as a count; `CTCD` and `CTUN`, the create-a-school colour
tables, are here with 0 rows. Which `TEAM` field selects a school's palette
entry is **not established** — `TPID` is 7 bits and `PACL` has 64 rows, which
fits and is not proof [A]. So the page offers names and no picker, and a test
asserts no colour field is ever drawn.

**The bound this row lives inside.** Member 0 is `RLE1`-packed and is itself
copied into `PL.QKL`, with its directory copied into `PL.QKL` and `FE.QKL`. A
name edit moves the encoding by **-13 to +1 bytes** against a slot one byte
larger than the bytes EA put in it [M]; a shorter encoding is written and its
cache copies rewritten, and the one that grew was refused by name (§3a).

### 3.4 Field Art & Create-Team Art — `field_art.textures`

**`offline-writer-proved`.** `FLDDATA.DAT` (1,422 members, 1,391 `LZH1`) and
`UIS_TMLO.DAT` (399 `LZH1` school logos) [M].

**The create-team half has nothing behind it and the reason is measured**: every
create-a-school table on this disc has 0 rows, because a created school is user
data in a memory-card save this studio does not read. Which field or which
school a member is remains unestablished — neither container names its members
and no table joins a `TEAM` row to a texture.

### 3.5 Stadiums — `stadiums.textures`

**`offline-writer-proved`.** `STADATA.DAT` (1,289 members: 1,195 `MMAP`, 45
`SMF`, 4 `DMF`) and `UIS_STAD.DAT` (245 stored) [M].

The disc also ships a real stadium **table** — `LEAGUE.DAT`'s `STAD`, 242 rows
of 56 fields — and its names are §3.3's, not this page's. The geometry is listed
and left alone: **no `SMF` or `DMF` decoder exists anywhere in this repository**.
`STADIUMS.DAT` is not opened at all — 197 MB, past the 144 MB read limit, and
its 2,914 members are 1,880 `SMF` and 1,034 empty, so there is no texture in it.

### 3.6 Presentation — `presentation.ui_textures`

**`offline-writer-proved`.** `FANDATA.DAT` (257 stored crowd members),
`MSCTDATA.DAT` (641: 240 `MMAP` and 400 `DMF`) and `LOADDATA.DAT` (46, thirty of
them 854×480) [M].

The scorebug itself is drawn by the executable from values it holds and nothing
on this disc has been mapped to it. `MOVIEDAT.DAT`'s 12 `MPCh` streams have no
decoder here and are not opened. Both sentences are on the page.

### 3.7 Menus & UI — `menus.text_members`

**`offline-writer-proved`.** Every `TEXT` string bank, measured: how many
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

The slot rule is the one that makes an edit reversible: a slot's *allocation* is
the room it has, running to the next slot less the terminator, so a bank a
previous edit shortened still shows the room its padding occupies.

**The writer that uses it is built.** `EXAMS.DAT`, `JERSEY.DAT` and
`OSDKSTRN.DAT` are named by **none** of the three caches [M], which is what
makes them safe to write; `GAMEDATA.DAT` — one `TEXT` member beside its 137
playbook databases — **is** named, by `FE.QKL` and `GAME.QKL`, and is refused
with both caches named. The lane is the shared
`mod_editor/games/_lanes/text_banks.py`, which Madden 09's text row also
instantiates. Real-disc proof in §3a.

`FONTS.DAT` and `UIS_FONT.DAT` hold 17 `FNTS` fonts [M]; no font decoder exists
here.

**The rest of this page is art.** The menu textures live across **51 further
containers** [M] — the 31 `UIS_*.DAT` (`UIS_BGSP.DAT` 689 `MMAP`,
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

### 3.11 Playbooks & Plays — `playbooks.databases`

**`offline-writer-proved`.** `GAMEDATA.DAT` holds 137 databases at members
4–140: one shared play library and 136 playbooks, all one schema shape [M].
**Their nineteen tables are name-for-name identical to Madden 09's nineteen** —
the closest the two discs come anywhere.

**One field is why the Madden writer did not port**: Madden's `PBPL` carries a
play `name` and this one's does not, so the names live in `PLYL` (192-bit
strings) and six further tables [M]:

| table | name-bearing rows | `name` width here |
|---|---:|---|
| `PLYL` | 4,322 | 192 bits |
| `PBST` | 3,266 | 128 |
| `PBFM` | 2,356 | 264 |
| `SGF\x00` | 2,086 | 32 |
| `SPKF` | 1,510 | 112 |
| `SETL` | 236 | 144 |
| `FORM` | 41 | 160 |

**13,817 name-bearing rows**, and **2,301 of the 2,603 tables are packed exactly
full** — so a rename is possible and an insertion is not. The lane renames and
never adds or removes a row.

That was a **new field map, not new code**: this row is the same
`_lanes/tdb_records.TdbRecordLane` the roster and identity rows stand on.

**Why the caches are cheap here.** Every one of `GAMEDATA.DAT`'s 150 members is
**stored, codec 0** [M], so a record edit cannot change a stored size and the
directory never moves — which matters, because two of the three caches name this
container: its directory twice and fifteen of its members once each, including
real playbooks at members 4, 33, 94 and 133. The real-disc trial rewrote member
4 and the verifier re-read **18 cache copies** off the destination (§3a).

**What a play *does* is not editable.** `ARTL` is 86 fields here against Madden
09's 110 and no column of it has been decoded, so a route, an assignment or a
blocking rule is out of reach and the row says so rather than implying
otherwise.

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

### 3.13 Saves — `saves.draft_class`

**`read-only-mapped`, and the only page whose source is not the disc.**

At the end of a dynasty season NCAA Football exports its graduating class to a
memory-card save that Madden imports as its draft pool —
`BASLUS-21769LClass08` for the NCAA 09 / Madden 09 pair — and **no table on this
disc holds one** [M]. It is produced at run time. So this row reads the save:
138,240 bytes (270 sectors of 512), header `46 00 40 06`, **1,600 records of 86
bytes** at offset 4 and a 636-byte zero trailer [S]. Per record it reports the
college id, the two names, the class, the redshirt flag, overall, squad number,
position, weight, height and the 21 rating bytes as a block.

**The record shape is corroborated by this disc.** Its own `PLAY` table is 86
fields of the same family two years apart, which is why the disc digests are
pinned on a row whose source is a save.

**It counts the empty slots, and that is the number that matters**: Madden 09
hangs on "initializing roster management" if any of the 1,600 is zeroed [S], so
"how many are empty" decides whether a class will load at all.

**It does not write one, on purpose.** A compiler for this exact file already
exists outside this repository, in the owner's own `NCAA-Draft-Class-Editor`;
a second implementation of one format is how two of them start to disagree. The
refusal says that, by name.

**The identifier learned a second kind of source.** A draft class is not a disc
and used to be refused as "no ISO9660 volume descriptor found" — a real NCAA
Football artefact turned away for not being an ISO. `Ncaa09DiscIdentifier` now
recognises it by length and header and says which of the two it was handed.

### 3.14 Build & Share — the shell's own page.

---

## 4. The two pages that state a reason instead of a lane

`game.json` carried nine page notes when five pages had a lane. It carries
**two** now, and both name a reason that is a fact about the game or the
research rather than about this module's progress [M]:

* **The Crib** is an ESPN NFL 2K5 feature and not an NCAA Football concept.
  Empty on purpose, and it will stay empty.
* **Gameplay**: the boot executable is `SLUS_217.52`, 7,294,796 bytes, sha256
  `dc1b3089…9c1f71ee`, PCSX2 CRC `B0157E6C`. **No patch site on it has been
  located by this project.** Every site is per-title research, and none of the
  five `sltiu` immediates Madden 09's playbook-editor-caps patch uses is an
  address in this executable — they are addresses in a different binary. A
  pnach writer with an empty translation table is a control that can only
  refuse, so the page carries the sentence instead of the scaffold.

"Not built yet" appears nowhere, which is the same standard the nine notes were
held to.

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
| `MMAP` images drawn, sampled 60 members per container | `UIS_GEAR.DAT` 60/60, `PLADATA.DAT` 47/79, `UNIFORM.DAT` 780/840 | `mmap_art.parse` + `undecodable_reason` |
| `TEXT` members measured | 1,247, 241,787 bytes | the text lane |
| `SCHl` streams | 8,021, 412 decodable | the audio lane |
| `BNKl` banks / sounds | 728 / 1,213, 753 with a rate | the audio lane |
| preload copy entries | 564 across three caches, 47 containers | `ea_ql01.collect` |
| writers proved on the retail disc | 6, every one PASS | §3a |
| conformance checks | 523 of 523 | `python -m mod_editor.games conformance` |
| lanes on the contract | 14, on 12 of 14 pages | `python -m mod_editor.games list` |
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

1. **Nothing has been booted.** Nine rows write bytes; **no image built from
   this disc has been run**, in an emulator or on hardware. Everything in §3a is
   a verifier re-deriving a claim from two files, and that is a different thing
   from a game loading a disc.
2. **No PCSX2 replacement pack has been loaded.** Every texture identity this
   module offers is **derived** from the texture's own bytes; none is confirmed
   by a dump, because no dump has been paired with `SLUS-21752`.
3. **No rating scale is known** — only its **bound**. The five bits hold 0..31
   and every value is in use; what the game draws from them is not established
   and no control says.
4. **No colour is editable**, because the `TEAM` table has no colour field and
   the `TEAM` → `PACL` link is unproved.
5. **Two databases are unread**, and the field type behind them is described,
   not decoded (§5). With them the recruit name pool, `RCFN` (8,191 rows) and
   `RCLN` (6,915), stays out of reach.
6. **`SMF`, `DMF`, `MPCh` and `FNTS` are named and never opened** — 3,301, 603,
   12 and 17 members [M]. No reader for any of them exists here.
7. **MicroTalk is refused, not approximated** — 7,609 streams.
8. **What a play *does* is not editable**: `ARTL`'s 86 columns are undecoded, so
   the playbook row renames and nothing more.
9. **Which school, player or coach an art member belongs to is unknown.** None
   of these containers names its members, and no table joins a row to a texture.
10. **NCAA Football 06 is not on this box**, so the on-disc `PLAY` record could
    not be diffed against the NCAA-06 draft-class format the owner's research
    decoded; that research is cited as [S] and used as a reading of field
    meanings, not as a measurement.

## 8. What the writers needed, and what is left

The table this section used to be said every writer this module could gain was
a **shared** writer waiting on a schema table or one missing piece. Six of the
eight have been built; here is the same table with the answers in it.

| writer | then | now |
|---|---|---|
| **TDB record writer** | needed a field map for this disc | **built ×3.** `_lanes/tdb_records.TdbRecordLane`, instantiated by the roster, identity and playbook rows here and by Madden 09's team-data row. The field map was the whole of the work; the lane was not written twice. |
| **Container member rewrite** | needed the three `QL01` caches kept in step | **built.** `_lanes/preload_coherence` rewrites every stale copy or refuses by name, and the verifier re-reads them off the destination. |
| **Text slot writer** | needed the container writer | **built.** Same base as Madden 09's. |
| **Playbook name writer** | needed a field map, not new code | **built**, and that turned out to be exactly right. |
| **`MMAP` art writer** | needed the decoder moved into `_formats` | **built ×6**, once the decoder moved. |
| **Identity writer** | had "no target on this disc" | **wrong, and corrected.** `TLNA`, `TMNC` and the colours really are absent — but `TDNA`, `TMNA`, `TSNA`, `CONF.CNAM`, `DIVI.DNAM`, `STAD`'s four names and `COCH`'s two are all here. It is a *different* writer, not a port, and that is what was built. |
| **Audio stream / bank writer** | needed the container writer and the caches | **still not built.** Both exist now, so this is the cheapest row left to lift; MicroTalk stays out of reach either way. |
| **Executable patches** | needed translations | **still nothing.** No site on `SLUS_217.52` is mapped. |

**What a writer for this disc still needs**, in the order it would pay:

1. **A boot.** One PCSX2 run of a rebuilt image is worth more than the next
   three lanes, because it is the only thing that turns nine
   `offline-writer-proved` rows into anything a player sees.
2. **One PCSX2 texture dump paired with this disc**, which turns every derived
   identity into a confirmed one across six art rows at once.
3. **TDB field types 13 and 14 named**, which opens the recruit name pool.
4. **The `TEAM` → `PACL` link**, which is the only thing between the identity
   row and a colour control.

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

### 8a.4 A test that named one surface

`tests/mod_editor/test_registry_add_rows.py` asserted that a newcomer does not
appear in a surface it did not claim, and it asserted it by naming **`saves`** —
a surface that had no explicit rule on the day the test was written, so its rule
read back as `_ESTABLISHED_GAMES`. NCAA Football 09's Saves row claimed that
surface, `registry_add_rows.py` wrote it a rule, and the example stopped being
an example. **Every surface now has an explicit rule**, so there is no
replacement to name either.

**Done now**: the property is asserted over *every* surface at once — a
newcomer is in none it did not claim, and no unwidened surface's rule moved.
That is both stronger than the assertion it replaces and free of a name the
next module has to come back and change. Same defect as §8a.1 and §8a.2 in a
third costume: a test that hard-codes what the registry happened to hold.

### 8a.5 Every file outside this module that changed

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
| `tests/mod_editor/test_registry_add_rows.py` | §8a.4 |
| `tests/mod_editor/test_madden09_ps2_uniform_art.py` | the art lane moved into `_lanes` and now says where its identity table is, so a test that patched a module constant sets the lane's attribute instead |
| `mod_editor/games/contract.py`, `conformance.py`, `CONTRACT_PINS.json`, `CONTRACT_CHANGELOG.md`, `tests/mod_editor/test_games_contract.py` | `SHARED_LANES_PACKAGE`: a game may compose a shared lane base as it composes a shared format. Committed alone, under the version procedure. |
| `tools/registry_add_rows.py` | `--replace-row`, for a row whose rung moved. Three of this module's rows needed it and the tool could only add. Committed alone. |
| `mod_editor/games/madden09_ps2/{team_data,text_lane,uniform_art,containers}.py` | the three bases only pay if both games instantiate them |

Nothing in `mod_editor/gui/studio_qt.py` or `mod_editor/__main__.py` changed, and
no `_formats` reader changed: **the shared readers opened this disc unmodified**,
which is the whole claim of §2.

---

## 9. Where the code is

```
mod_editor/games/_formats/
  ea_ql01.py         the QL01 preload-cache format: parse, attribute a copy to
                     the container whose bytes it is, collect, build one
  mmap_art.py        the MMAP pixel codec, shared since the art rows needed it
mod_editor/games/_lanes/
  iso_tools.py       the ISO writer and verifier shims, and the range helpers
  preload_coherence.py  rewrite every stale cache copy, or refuse; and check
  synthetic_art.py   the MMAP fixtures both games are proved on
  tdb_records.py     TdbRecordLane -- a record edit, plan to verdict
  terf_art.py        TerfArtLane / TerfArtWriteLane -- a texture member
  text_banks.py      TextBankLane -- a string slot, rewritten in place
mod_editor/games/ncaa09_ps2/
  __init__.py        GAME, IDENTITY, the fourteen lanes, the studio window
  containers.py      disc access, container reports, the QL01 caches, the
                     writer-side open_for_rewrite, and the synthetic disc
  disc_identity.py   which image this is -- and now, which SAVE this is
  inventory_lane.py  3.12      database_lane.py   3.2      identity_lane.py  3.3
  text_lane.py       3.7       texture_lane.py    3.1      art_pages.py    3.4-3.6
  playbooks_lane.py  3.11      saves_lane.py      3.13     audio_lane.py     3.9
tools/validate_ncaa09_ps2_{inventory,databases,identity,text,textures,
                           uniform_disc_art,art_pages,playbooks,saves,audio}.{sh,bat}
tests/mod_editor/test_ncaa09_ps2_module.py    the harness and the fragment check
tests/mod_editor/test_ncaa09_ps2_lanes.py     53 tests over the lanes
docs/product/measured/ncaa09_ps2/tdb-schema.json
```

Every lane runs without a window, and every one takes `--selftest` instead of
`--source`, which runs it on a synthetic disc and needs no game data at all:

```
python3 -m mod_editor.games.ncaa09_ps2.database_lane   --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.identity_lane   --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.playbooks_lane  --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.text_lane       --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.texture_lane    --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.art_pages       --page stadiums --source "<your>.iso"
python3 -m mod_editor.games.ncaa09_ps2.saves_lane      --source "<your class>.bin"
```

A writer also takes `--recipe` and `--destination`, which plans, builds a NEW
image and runs the independent verifier over the result; `--dry-run` stops after
the plan and prints the byte ranges.

## 10. The studio

`python -m mod_editor.games` lists **PS2 NCAA 09 Studio**, Ready, **14 lanes**,
alongside the other two PS2 studios — the same lane count Madden 09 carries.

Opened headless (`QT_QPA_PLATFORM=offscreen`), the window draws **fourteen pages
in the shell's order** [M]:

| # | page | widget | lane(s) |
|---:|---|---|---|
| 1 | Uniforms & Equipment | two lane panels | `uniforms.texture_census`, `uniforms.disc_art_writer` |
| 2 | Names, Numbers & Faces | two lane panels | `players.league_databases`, `rosters.face_textures` |
| 3 | Text & Team Identity | `LanePage` | `identity.league_records` |
| 4 | Field Art & Create-Team Art | `LanePage` | `field_art.textures` |
| 5 | Stadiums | `LanePage` | `stadiums.textures` |
| 6 | Presentation | `LanePage` | `presentation.ui_textures` |
| 7 | Menus & UI | `LanePage` | `menus.text_members` |
| 8 | The Crib | `UnavailablePanel` | — |
| 9 | Audio | two lane panels | `audio.streams`, `audio.banks` |
| 10 | Gameplay | `UnavailablePanel` | — |
| 11 | Playbooks & Plays | `LanePage` | `playbooks.databases` |
| 12 | All Textures | `LanePage` | `textures.container_inventory` |
| 13 | Saves | `LanePage` | `saves.draft_class` |
| 14 | Build & Share | `BuildPage` | the shell's own |

Fourteen lanes on twelve pages, two `UnavailablePanel`s each carrying their
page's sentence, and the shell's build page. No page is missing and none is
silently empty.



The third game on the Game Studio shell. Like Madden 09 it ships no window of
its own: `studio_window` points at the core shell, which draws the same fourteen
pages every studio has. A lane reaches its page by being a lane; a page with no
lane says why in one sentence.

This document is the honest inventory: what each page does, what is measured,
what is merely sourced, what is assumed, and — at the end — the list of things
this module deliberately does **not** claim.

**Fourteen registry rows fill twelve of the fourteen pages** (§3): **nine
write**, two export, three inspect. Every writer is proved offline twice — on a
synthetic disc in CI, and by hand on the retail image, with the numbers in §3a.
**Nothing has been booted**: no image built from this disc has been run in an
emulator or on hardware, and no row says otherwise. §11 answers the seven-point
shipping standard for the module as it stands.

**Evidence tags, on every load-bearing claim.**
**[M]** measured — a read-only command was run against a disc this box holds and
the number is quoted. **[S]** sourced — someone else's finding, cited.
**[A]** assumed — inference, not verified; treat it as a question.

**Retail-free.** Everything below is a name, an offset, a length, a count or a
digest. No member payload, no decoded pixel and no string from the game appears
here or in the code.

---

## 11. The shipping checklist

The seven-point standard from `ADDING_A_GAME_MODULE.md`, answered for this
module as it stands.

1. **Every page has its answer** — **yes.** Twelve pages carry a lane; two carry
   a measured sentence; one is the shell's. Neither of the two is blocked on a
   repository-layout fact, which is what the previous answer to this question
   had to admit: the `MMAP` decoder's location was in the way of four pages and
   it is not any more.
2. **Every writer is proved twice** — **offline twice, never in game.** Each of
   the nine writers is proved by the conformance harness on a synthetic disc and
   by hand on the retail image (§3a), with an independent verifier that imports
   none of the writer and an adversarial byte flip that it refuses. **Neither
   proof is a boot**, and §7.1 says so first.
3. **Art round-trips** — **yes.** A texture decodes to PNG, is re-indexed
   against the member's own CLUT, is laid out again, re-packed, written into a
   new image, and decoded back out of that image as the PNG that was given.
   Proved on `PLYRFACE.DAT` and `UIS_STAD.DAT` on the retail disc.
4. **Rosters, team data and text have writers with the four CRCs proved** —
   **yes.** All three, and the CRCs are recomputed on every write and re-derived
   from the destination's own bytes: 6 slots on a roster member, 52 on the
   league database, 40 on a playbook, and 8,564 of 8,564 across the disc before
   any write existed.
5. **Audio, stadiums, playbooks and gameplay patches at the rung their formats
   permit** — **three of four.** Stadiums and playbooks are
   `offline-writer-proved`. Audio is still `extract-only`: the container writer
   it was waiting on now exists, so this is the cheapest row left to lift, and
   MicroTalk stays out of reach either way. **Gameplay: no**, and §4 says why.
6. **Validators run in a shipped tree and on a real cmd.exe** — **half.** All
   **ten** `.sh` validators were run inside a staged release tree and printed
   their `NCAA09_PS2_*_VALIDATION_PASS` token there. The ten `.bat` mirrors are
   written without parentheses inside `if` blocks and have **not been run on a
   real cmd.exe from here**.
7. **Nothing is claimed above its proof** — every row sits on the rung its
   evidence earns, no row is hidden, and §7 is the list of what is not claimed.
   The one thing that would move most of it is a boot.

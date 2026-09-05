# Madden NFL 09 (PlayStation 2) — what the module does today

The second game on the Game Studio shell, and the first written *for* it: the
module ships no window of its own. `studio_window` points at the core shell,
which draws the same fourteen pages every studio has. A lane reaches its page
by being a lane; a page with no lane says why in one sentence.

This document is the honest inventory: what each page does today, what is
measured, what is merely sourced, what is assumed, and — at the end — the list
of things this module deliberately does **not** claim.

**Fourteen registry rows fill eleven of the fourteen pages** — eleven of them
write, two export, one inspects (§3) — and **nothing has been booted** (§7,
§7a). Every claim about a written image is about its bytes. §10 answers the
seven-point shipping standard for this module as it stands today.

**Evidence tags, on every load-bearing claim.**
**[M]** measured — a read-only command was run against a disc this box holds
and the number is quoted. **[S]** sourced — someone else's finding, cited.
**[A]** assumed — inference, not verified; treat it as a question.

**Retail-free.** Everything below is a name, an offset, a length, a count or a
digest. No member payload, no decoded pixel and no string from the game
appears here or in the code.

---

## 1. The discs

Two images are recognised, and they are **not the same disc** [M]:

| | retail | Deluxe |
|---|---|---|
| serial | `SLUS-21770` | `SLUS-21770` |
| boot file | `SLUS_217.70` | `SLUS_217.70` |
| boot ELF SHA-256 | `adb400ba…f9f68c4c` | `d1cb5459…7588a515` |
| PCSX2 CRC | `38014255` | `084562FF` |
| image SHA-256 | `b34e8a6a…a82f6427` | `d331c5e4…4bc1be20` |
| image bytes | 1,657,339,904 | 1,846,476,800 |
| files | 187 | 185 |

The serial alone is not specific enough to act on, so the identifier keys on
the **boot ELF digest** and says which edition it found. Thirteen `/DATA`
files differ between the two [M] — the Deluxe team rewrote the uniform,
stadium, field-art and database containers — so a lane that reads
`UNIFORMS.DAT` genuinely gets different bytes depending on which disc is open.

A disc booting another serial is refused with one sentence naming what was
expected. A Madden 09 re-cut whose ELF matches neither digest is **not**
refused: it is reported as `unknown edition`, catalogued like any other, and
nothing about it is claimed. Every lane here is read-only, so nothing is
risked by listing it.

Identity comes from `Ps2DiscIdentifier` (ISO9660 volume + `SYSTEM.CNF` +
boot ELF) with the edition layered on top in `disc_identity.py`.

---

## 2. The containers, and the one rung everything stands on

Every large `/DATA/*.DAT` is an EA `TERF` container. That format is fully
decoded and documented in [`EA_TERF_FORMAT.md`](EA_TERF_FORMAT.md) — header,
chunk chain, member directory, codec table and the two implemented codecs —
and the reader is shared (`mod_editor/games/_formats/ea_terf.py`), so this
module contributes the *game-specific* half only: which files to walk, how
much of one it will hold in memory, and how to recover a container the disc's
own directory record understates.

Three facts from that document shape every lane below:

1. **Member offsets are relative to the `DATA` tag, not its payload** [M].
2. **An empty member still occupies one alignment unit** [M].
3. **A packed member's stored magic tells you nothing** [M] — 39 of 107
   containers change classification between their stored and decompressed
   bytes, so a member is classified only after it is unpacked.

And one that used to shape what was *not* here: **`LZH1` had no encoder**, in
this repository, in the owner's, or anywhere public [S]. There is one now
(`EA_TERF_FORMAT.md` §5.3), written from the grammar rather than lifted from
anything, and **1,836 of 1,836** compressed members of the three art containers
re-encode and decode back byte for byte at about the size EA shipped them [M].
Storing a member uncompressed remains the fallback and is a shape the shipped
game already loads — the retail disc itself ships 270 of `UNIFORMS.DAT`'s 725
members that way inside a `COMP` container [M]. What the encoder does *not*
settle is whether the game loads a container this module rebuilt; that is §7's
first item, and no writer here pretends otherwise.

### 2.1 Container size limit

The module reads a container up to **96 MB** and lists anything larger with
its size, unread. Madden 09's six speech and music containers run 124 MB to
415 MB [M]; counting their members is not worth half a gigabyte of memory, and
"listed but not read" is a state the catalogue names rather than a silent gap.

---

## 3. The pages

The shell draws the same fourteen pages for every game, in its own order
(`PAGE_ORDER`, `mod_editor/games/contract.py`). Madden 09 fills **eleven** of
them with **fourteen registry rows**; **The Crib** and **Saves** state a reason
instead of carrying a lane (§4); **Build & Share** is the shell's own page.

| § | page | row(s), all prefixed `madden09ps2.` | rung |
|---|---|---|---|
| 3.1 | Uniforms & Equipment | `uniforms.mmap_export` · `uniforms.disc_art_writer` | `extract-only` · `offline-writer-proved` |
| 3.2 | Names, Numbers & Faces | `players.team_databases` · `rosters.face_textures` | `offline-writer-proved` · `offline-writer-proved` |
| 3.3 | Text & Team Identity | `identity.team_records` | `offline-writer-proved` |
| 3.4 | Field Art & Create-Team Art | `field_art.textures` | `offline-writer-proved` |
| 3.5 | Stadiums | `stadiums.textures` | `offline-writer-proved` |
| 3.6 | Presentation | `presentation.ui_textures` | `offline-writer-proved` |
| 3.7 | Menus & UI | `menus.text_members` | `offline-writer-proved` |
| 3.8 | The Crib | — | by design, §4 |
| 3.9 | Audio | `audio.streams` · `audio.banks` | `offline-writer-proved` · `extract-only` |
| 3.10 | Gameplay | `gameplay.executable_patches` | `offline-writer-proved` |
| 3.11 | Playbooks & Plays | `playbooks.databases` | `offline-writer-proved` |
| 3.12 | All Textures | `textures.container_inventory` | `read-only-mapped` |
| 3.13 | Saves | — | by design, §4 |
| 3.14 | Build & Share | — | the shell's own |

**Eleven rows write, two export, one inspects. None is `runtime-proved`**, and
none can be from this box: no rebuilt Madden 09 image has been loaded by the
game (§7). Every writer takes a read-only source and produces a **new** image
whose length is the source's, declares the byte ranges it touched, and ships a
verifier that imports none of it.

### 3.1 Uniforms & Equipment — the `MMAP` art, out and back

Two rows, because the exporter shipped first and earns a lower rung than the
writer that followed it. Both read the same four containers —
`UNIFORMS.DAT`, `PLYRFACE.DAT`, `COACFACE.DAT`, `TATTOOS.DAT` — through the
same catalogue and the same decoder.

**`uniforms.mmap_export`, `extract-only`.** Catalogues, previews and exports
the uniform, player-face, coach-face and tattoo textures as PNG. Measured on
the retail disc [M]: **1,780 texture members, 7,616 images, 7,082 decodable**,
534 refused. Widen the same decoder to ten containers and **11,039 of 12,779 images
decode**, with every refusal in one of three groups the catalogue names rather
than a silent gap [M]:

| refused | why |
|---:|---|
| 1,188 | pixels stored under EA codec 4, `IPU1` — every `UIS_MCFL` member and nothing else. Not decoded here. |
| 453 | a palette-only image entry: it carries alternate CLUTs for another image and has no pixels of its own. Not a failure. |
| 99 | no palette — the `PLYRFACE` hairstyle entries, whose colour Madden picks at run time. |

Whole-disc catalogue with an export and its verify: **about four minutes** [M] — the cost
of 1,780 `LZH1` members in pure Python, and the reason the studio runs a
catalogue in a child process with progress. Only the *surface* table is at the
front of an `MMAP` member; the image, palette and name tables are past the
pixels, so there is no prefix shortcut.

**Import is checked, not decorative.** A PNG must be exactly the texture's
size or an exact whole-number multiple, 8-bit, non-interlaced, RGB or RGBA;
anything else is refused naming the size that was wanted. A same-size PNG is
indexed against the texture's *own* palette and the result reported — a
Madden 09 texture rides its own CLUT, so a colour that palette does not carry
cannot be introduced, and the user is told how many pixels landed exactly
instead of finding out later.

**`uniforms.disc_art_writer`, `offline-writer-proved`.** The other direction:
an edited PNG back into the `MMAP` member it came from, in a **new** disc
image. Three encoders had to exist first, and all three are proved offline:

1. **`LZH1`** (`ea_terf.lzh1_compress`) — codec 5 had no public encoder.
   **1,836 of 1,836** members of `UNIFORMS.DAT`, `STADIUMS.DAT` and
   `FIELDART.DAT` re-encode and decode back byte for byte under two
   independent decoders and both read modes; aggregate 1.0078× EA's, median
   0.9896×, 65% of members smaller or equal [M].
   [`EA_TERF_FORMAT.md`](EA_TERF_FORMAT.md) §5.3.
2. **`MMAP`** (`mmap_art.encode`) — header, surface table, pixels, palette
   table, palettes, name table, image table, each 16-byte aligned, the member
   ending unpadded at the image table, an extra table carried through as an
   opaque tail. **All 1,780 `MMAP` members of the four art containers rebuild
   byte for byte from their own decoded pixels** [M]. Where a CLUT carries a
   duplicate colour — 420 of the 1,780 do — indexing from pixels alone has more
   than one right answer, so a rewrite keeps the index the file used wherever a
   pixel is unchanged.
3. **Relocation in the ISO9660 writer** — opt-in, for a rebuilt container that
   will not fit the extent it owns. Fixed allocation stays the default and is
   the ordinary outcome.

**How the write is bounded.** A member is re-packed under `LZH1` (or stored,
which this container family already ships) and the container is laid out again;
the image length never changes. **The preload caches are part of the writer,
not a footnote:** `GAME.QKL` and `FE.QKL` carry byte copies of container
directories and of individual members and the game preloads from the copy.
`UNIFORMS.DAT`'s directory is copied **three times** — once in `GAME.QKL`,
twice in `FE.QKL` — and none of its members at all [M], so a member rewrite is
free only while the container's first `data_offset` bytes stay put, and they
move the moment a member changes stored size or codec.
`containers.preload_copies(image)` is the shared reader — **6,270 copies across
39 containers, every one byte-identical to what it copies** [M] — and the
writer rewrites every stale copy, declares the ranges, and refuses a *carried*
member whose stored size changed, because a cached copy is a fixed slot.

**What the verifier checks.** `verify` re-decodes every exported texture
straight from the user's disc **by key**, not through the catalogue that
produced the receipt, and fails on a tampered file, a missing one or an
undeclared one. For a build it adds `ps2_iso9660_verify.verify_replacement`
for the image-level claim, compares every untouched member of every rebuilt
container byte for byte, re-reads every preload-cache copy off the **new**
image, and decodes the rewritten texture out of the new image.

**Real-disc proof** [M]: image 1 of `UNIFORMS.DAT` member 158 (128×128)
replaced with a red/blue swap of itself — re-packed under `LZH1` at 131,010
bytes against 132,881, container 55,741,504 inside its 55,743,360-byte extent,
image still **1,657,339,904 bytes**, three cached directories rewritten,
10,464 of 16,384 pixels exact (worst channel 89, the cost of riding a fixed
CLUT), **724 untouched members byte-identical**, and the independent ISO9660
verifier re-deriving all 72,956,677 declared bytes with 1,584,383,227 bytes
compared unchanged, in 105 seconds; the destination was deleted afterwards.

**What still needs a boot.** That the game loads a rebuilt `UNIFORMS.DAT` at
all, and that the recoloured sheet appears on a player. Separately, **Write
PCSX2 pack is still not offered from either row**: `replacement_identity`
answers for a texture a dump has shown being drawn (§6.5) and `None`, with a
sentence saying what would produce an answer, for one that has not — and no
pack built from those names has been loaded in an emulator.

**How the textures are grouped, and what is not known.** `PLYRFACE` and
`COACFACE` name their single image `FACE`, and `TATTOOS` names its own [M], so
those groups come from the file. `UNIFORMS.DAT` names **nothing** — 455
members, about fifteen unnamed images each — so the member index is the only
structure it offers, and **which team a member belongs to is not established
from the disc** [A]. §6.5 narrows it from the capture instead.

### 3.2 Names, Numbers & Faces — the team databases, and the faces

Two rows on one page: the rows of the disc's own databases, and the art of the
faces those rows describe.

#### 3.2.1 `players.team_databases` — the EA TDB databases

**`offline-writer-proved`.** Madden 09's team, roster and tuning data lives in
**EA TDB v8 databases packed as `TERF` members** — plus one bare database,
`/DATA/STRMDATA.DB`, with no container around it [M]. The reader is shared:
`mod_editor/games/_formats/ea_tdb.py`.

**Measured on the retail disc** [M]:

```
355 databases   (235 in DB_TEAMS.DAT, 104 in GAMEDATA.DAT,
                 15 in TEMPLATE.DAT, 1 bare STRMDATA.DB)
4,108 tables · 85,400 field definitions
```

Whole-disc walk: **about nineteen seconds** [M]; the catalogue with its rows,
about twenty-nine. The catalogue carries **field names, not field values**. A
field name is the schema and is identical on every disc; a record's contents
are the user's game data. A test asserts the point by searching the serialised
catalogue for the synthetic fixture's own string values and failing if it finds
one.

**Three things the TDB reader had to get right**, each measured rather than
assumed:

- **Records are bit-packed LSB-first**, within the byte and within the field
  [M]. Some documentation of this format says MSB-first; under that reading the
  same bytes give a different team id for every player on one team and the same
  speed rating for all of them. LSB-first was cross-checked against three
  independent existing readers and validated field-by-field against five real
  databases: **2,321 records, 7,797 field definitions, zero mismatches** [M].
- **`version` is the only big-endian field in the header** [M]. Read
  little-endian it comes back 2048; read big-endian, 8. This is why two readers
  can disagree about the version of one file.
- **Strings are latin-1, never utf-8** [M]. EA stores 8-bit characters; a utf-8
  decoder mangles them or refuses.

A fourth was found later and is §3.11's: **a four-character table name is four
bytes, not four characters**. Until `decode_name` was written, 103 of the 355
databases were refused by the reader because they declare a table named
`SGF\x00`.

**The four checksums, computed before anything was written with them.** EA
stores four CRC-32/MPEG-2 values in every TDB — a file-header CRC over the
header's first 20 bytes, a *prior-block* and a *header* CRC per table, and an
end-of-file CRC over the last table's data — and a Madden save with a stale one
is refused by the game outright [S]. `verify_crcs` was run over every TDB on
the retail disc: **8,926 of 8,926 checksum slots across all 355 databases hold
the value they recompute to, 0 mismatches** [M]. Before the name fix the same
pass covered 4,806 slots across 252 databases, also with 0 mismatches.

**What it writes.** `/DATA/DB_TEAMS.DAT` only, and inside it two tables:

- `PLAY` — first name, last name, jersey number, age, and twenty ratings
  (`POVR PSPD PACC PAGI PSTR PAWR PCTH PCAR PTHP PTHA PJMP PTAK PBTK PPBK PRBK
  PSTA PINJ PKPR PKAC PMOR`). The list is explicit in `PLAYER_FIELDS`, not
  "whatever is numeric", so what the page offers is something a reader can
  check. A rating stops at **99** — the scale the game's own data is on — not at
  the 127 its seven-bit field would hold. A name stops one byte short of its
  field so the terminator survives.
- `TEAM` — `TDNA` nickname, `TLNA` city, `TSNA` abbreviation, `TMNC` short
  name. Which column is which was settled by reading all 32 team records off a
  retail disc and seeing what each consistently held [M]; no value from that
  reading is stored in this repository.

On the retail disc that is **12,499 editable rows** across 235 databases [M].
Height and weight are deliberately absent: `PWGT` looks like pounds less 160 on
the records sampled, and "looks like" is not a unit this page will label a
spinner with.

**How the write is bounded.** A TDB field owns a fixed run of bits in a
fixed-stride record, so a record edit **cannot change a length**. The database
comes back the same size, so the `TERF` member does, so the container does —
measured: `rewrite_member` handed a member's own bytes reproduces
`DB_TEAMS.DAT` byte for byte [M] — so the ISO extent is rewritten in place and
the destination is the source's exact size. All four invariants are checked at
build time and refused rather than approximated. `DB_TEAMS.DAT` is named by
neither preload cache [M]; `containers.preload_names` reads that list off the
user's own image, and any container it names is refused. `/DATA/GAME.QKL` and
`/DATA/FE.QKL` name 29 and 28 `/DATA` files and carry at least some of them
verbatim — the first 256 bytes of `UIS_BANR.DAT`, `UNIFORMS.DAT`,
`PLYRFACE.DAT`, `GAMEDATA.DAT`, `TEMPLATE.DAT` and `LOADDATA.DAT` each appear
inside the cache that names them [M]. Not every named file is demonstrably
copied — `STADATA.DAT` is named in both and its head is in neither [A] — so the
refusal is the conservative reading. `STRMDATA.DB` is out of this row's scope:
a 5 MB bare database of league and presentation tables with no `PLAY` table
[M]; §3.3 writes its `TEAM` rows.

**What the verifier checks.** It imports none of the writer: it runs
`ps2_iso9660_verify.verify_replacement` for the container-level claim,
re-parses the destination's member with the plain reader to read every edited
value back, re-derives all four checksums from the destination's own bytes, and
byte-compares the edited member against the source requiring every differing
byte to fall inside a declared field span or a checksum slot. Its tests prove
it fails on a byte flipped outside the declared ranges, on a record changed
behind the receipt's back *inside* a declared range, and on a stale checksum.

**Real-disc proof** [M]: `DB_TEAMS.DAT` member 0, `PLAY` record 0 — first name,
last name and jersey number — **2,585,800 bytes declared in two ranges**, a
1,657,339,904-byte destination built in 89 s, and the verifier passing with
three values read back, **all 44 checksum slots** of the edited database
correct, **0** bytes changed outside a declared span, and `ps2_iso9660_verify`
comparing 197 entries and 1,654,754,104 unchanged bytes (§7a).

Also measured and recorded rather than used as a bound [M]: `lenBits` is
`lenBytes * 8 - 1` in 561 of 561 tables (it is *not* the last field's end);
index blocks trail the record array rather than preceding it; and `dbSize` is
the last table's end plus four, not the file length.

**What still needs a boot.** That the game loads the rebuilt `DB_TEAMS.DAT` and
shows the renamed, re-numbered player on a roster screen.

#### 3.2.2 `rosters.face_textures` — the faces, tattoos and menu portraits

**`offline-writer-proved`**, and one lane doing both halves: preview, **Export
PNG**, a checked **Import PNG**, and a **Build** that writes the edited texture
into a new disc image. **Edits 4,611 `MMAP` members** across `PLYRFACE.DAT`,
`COACFACE.DAT`, `TATTOOS.DAT` and `UIS_PLYR.DAT` — 532 player faces and 711
coach faces at 128×128, 82 tattoos, 3,286 96×96 menu portraits; **4,599 of the
4,611 images decode**, and the twelve that do not declare a pixel layout the
decoder does not implement and are refused by name [M]. Catalogue: 41.8 s, the
slowest of the art pages because 711 coach faces are `LZH1` [M].

**Does not edit** a player's name, number, team or ratings — those are
§3.2.1's — and **does not know** which player a face or a portrait belongs to,
because neither container names its members [A].

Bounding, caches and verifier are §3.1's, exactly: the same lane class with a
different container list. `PLYRFACE.DAT` has 2 directory copies and 29 member
copies in the caches, `COACFACE.DAT` 2 and 4, `TATTOOS.DAT` 1 and 0,
`UIS_PLYR.DAT` 3 and 1 [M] — every one kept in step or the edit refused by
name.

**Real-disc proof:** none of this row's own four containers has been written on
a real disc. The three real-disc art trials that exist (§3.4, §3.5, §3.6) ran
this same lane code against a different container list, and §3.1's ran the
identical write path against `UNIFORMS.DAT`. That is stated rather than
borrowed.

**What still needs a boot:** an edited face or portrait appearing on a player,
on a rebuilt disc. Lane document:
[`MADDEN09_PS2_ART_PAGES.md`](MADDEN09_PS2_ART_PAGES.md).

### 3.3 Text & Team Identity — the thirty-two teams' names and colours

`identity.team_records`, **`offline-writer-proved`**. One target is a **team**,
not a record: the lane lists 32, each labelled from the values read off the
user's own image, each offering seven controls — `TDNA` nickname (17 bytes),
`TLNA` city (18), `TSNA` abbreviation (7), `TMNC` short name (17), a primary
colour as `TBCR`/`TBCG`/`TBCB`, a secondary as `TB2R`/`TB2G`/`TB2B`, and the
`CYID` city id. Widths are read off the file's own field directory at run time,
never from a table written down in the lane [M]. Text is latin-1, NUL-padded,
offered one byte short of its field so the terminator survives. The record has
no alpha channel, so `#AARRGGBB` is accepted and **the alpha byte is dropped**,
which the field's own help text says. A blank box means *keep what is there*.

**Fields measured and deliberately not offered** [M]: `TCDO`, `TGPT` and `TCTX`
track `TGID` on 32 of 32 teams and `TCRP` tracks `TGID − 1` on 31 of 32 — all
consistent with a colour or logo index [S] and with several other readings, so
offering one would be asking the user to run the experiment.

**How the write is bounded, and how far it reaches.** A rename that reaches one
copy of a team's identity and not the others leaves the game reading whichever
it opened first, so the blast radius was measured first. Three copies carry all
32 teams' identity fields: `DB_TEAMS.DAT` members 0..31 (the anchor),
`STRMDATA.DB`'s `TEAM` table (234 rows, **32 of 32 identical to the anchor**),
and `TEMPLATE.DAT` member 1 (**32 of 32 identical**) [M]. **One recipe writes
the first two**, so a rename cannot leave them disagreeing; on the retail disc
32 edited teams write **64 rows** [M]. `STRMDATA.DB`'s rows are **not in `TGID`
order** — team 1 is record 106, team 4 is record 0 — so the second copy is
resolved by reading the field off every record, never by arithmetic on a
position. Agreement is checked field by field on the values being written: a
row that already differs is left alone and the receipt names the field that
made it differ. The third copy is refused (§4). The write itself is the same
fixed-bit-run rewrite as §3.2.1 — `ea_tdb.write_records`,
`ea_terf.rewrite_member`, `ps2_iso9660_writer.replace_files`, **imported and
not copied**, so the two pages cannot drift apart on the one thing they both
do.

**What the verifier checks.** `verify_build` imports none of the writer and
proves five things: outside the declared ranges the destination is the source
and no untouched extent moved; every edited value reads back from the
destination's own container, member, table, record and field, and from the bare
database beside it; every differing byte inside an edited database lies in a
declared field span or a checksum slot; all four kinds of checksum agree with
the bytes that are there; and every written name is the text followed by
**NULs to its own field's width**, the padding rule re-expressed in the
verifier rather than borrowed from the encoder. Each of the five has a test
that makes it fail.

**Real-disc proof** [M]: one team's abbreviation and primary colour, written to
`DB_TEAMS.DAT` member 0 and `STRMDATA.DB` `TEAM` record **106** — matched by
`TGID`, not by position — **7,746,536 bytes declared in four ranges**, a
destination the source's exact size, and **PASS**: 8 values read back, 2
databases re-parsed, **470 of 470 checksum slots correct**, 0 undeclared
changed bytes, 197 entries and 1,649,593,368 unchanged bytes compared. Two
adversarial flips were refused — one byte outside every declared range, one
byte inside a declared ISO range — and the untouched image then re-verified
PASS.

**What still needs a boot.** The owner opens **Team Select**, finds the edited
team, reads the renamed abbreviation and sees the new primary colour on the
helmet and jersey preview. Three further questions a boot would settle: whether
the `TEMPLATE.DAT` copy this page refuses shows the old name anywhere a user
would see it; whether `CYID` alone moves anything on screen; and whether any of
`TCDO`/`TCRP`/`TGPT`/`TCTX` is in fact a logo index. A **known** gap, not a
question: a team's name is also prose — **543 of the 14,748 `TEXT` members
carry at least one of the 32 teams' four identity strings, 464 of them a string
five characters or longer**, across six containers [M] — and this page does not
touch them; §3.7 is where a string is edited. Lane document:
[`MADDEN09_PS2_IDENTITY.md`](MADDEN09_PS2_IDENTITY.md).

### 3.4 Field Art & Create-Team Art — `FIELDART.DAT`

`field_art.textures`, **`offline-writer-proved`**. **Edits the container's 73
`MMAP` textures, every one of which decodes** — 69 at 128×128 and four at
1024×256 [M]. Catalogue: 715 members walked, 4.7 s [M].

**Does not edit** the other **642 members, all `SMF` geometry** — nine in ten
of the file. No decoder for `SMF` is built anywhere in this repository and no
layout for it is documented here, so the catalogue counts them by format and
the lane leaves them alone. **Does not create a team**: the create-team art
this page is also named for has not been located on this disc by this project,
and the page says so rather than offering a control that could only refuse.

Bounding, caches and verifier are §3.1's. `FIELDART.DAT`'s directory is copied
**three times** and none of its members [M], so a re-packed member moves the
directory and all three copies are rewritten with it.

**Real-disc proof** [M]: `FIELDART.DAT:647:0`, 128×128, replaced with a
synthetic PNG of diagonal bands cycling that texture's *own* CLUT — re-packed
under `LZH1` from 7,704 to **1,408** stored bytes, container 7,380,032 →
7,373,696, **image length unchanged**, all three cached directory copies
rewritten at 11,584 bytes each, **6 ranges / 24,593,349 bytes declared**, and
the verifier passing with 714 untouched members byte-identical, 3 cache copies
re-read off the new image, and the rewritten texture decoding out of the new
image at **16,384 / 16,384 pixels exact, maximum channel error 0**.

**What still needs a boot.** `FIELDART.DAT` member 647 was drawn in the
Bears-versus-Vikings coin-toss frame [M], so that is the screen to look at.
Lane document: [`MADDEN09_PS2_ART_PAGES.md`](MADDEN09_PS2_ART_PAGES.md).

### 3.5 Stadiums — `STADIUMS.DAT`, `STADATA.DAT`

`stadiums.textures`, **`offline-writer-proved`**. **Edits the 514 `MMAP`
texture members** of the two stadium containers, **581 of whose 624 images
decode** [M]. Catalogue: 1,623 members walked, 7.5 s [M].

**Does not edit** the **805 `SMF` and 2 `DMF` geometry members in the same two
containers** [M] — a stadium's shape, its stands, its scoreboard mesh and its
crowd. They are counted by format per container and left alone. **Does not
know** which stadium a texture belongs to: neither container names its members
[A]. Five members of `STADIUMS.DAT` — 828 to 832 — are **palette banks**: 45
alternate CLUTs each and no surface at all, so there are no pixels in them to
draw [M]. A palette bank is a real thing this format has, not a damaged member,
and the lane counts it, lists it and refuses it by name; fifteen further images
declare no palette, and 23 in `STADATA.DAT`, each refused by name rather than
drawn wrong [M].

Bounding, caches and verifier are §3.1's. `STADIUMS.DAT` has 3 directory copies
and 1 member copy; `STADATA.DAT` has 0 directory copies and **67** member
copies [M].

**Real-disc proof** [M]: `STADIUMS.DAT:697:0`, 128×128, replaced with a
synthetic own-CLUT PNG — re-packed under `LZH1` from 17,516 to **654** stored
bytes, container 68,809,408 → 68,792,576, **image still 1,657,339,904 bytes**,
all three cached directory copies rewritten at 21,824 bytes each, **6 ranges /
86,022,725 bytes declared**, verifier PASS with 1,354 untouched members
byte-identical, 4 cache copies re-read, **16,384 / 16,384 pixels exact,
maximum channel error 0**.

**What still needs a boot.** The same Bears-versus-Vikings coin toss drew
member 697 [M]; an edit that shows up in one stadium and not another would also
settle which member belongs to which venue, which is not established here. Lane
document: [`MADDEN09_PS2_ART_PAGES.md`](MADDEN09_PS2_ART_PAGES.md).

### 3.6 Presentation — 48 `UIS_*.DAT`, `LOADDATA.DAT`, `ICONS.DAT`

`presentation.ui_textures`, **`offline-writer-proved`**. **Does not edit the
scorebug or the broadcast overlays** — they are drawn by the executable from
values it holds, not from a data file, and nothing on this disc has been mapped
to them (§4). **What it does edit is the art those screens draw: 7,678 `MMAP`
members across 50 containers, 6,482 of their 7,832 images decodable** [M].
Forty-eight `UIS_*.DAT` files are on the disc and **33 carry `MMAP` members**;
the other 15 carry fonts (`FNTS`), nested `TERF` containers, or members whose
first 32 bytes match no format id this reader knows [M]. Catalogue: 8,041
members walked, 19.3 s [M] — the 48 `UIS_*.DAT` on their own take 9.8 to 11.1
seconds over two runs, and the rest is `LOADDATA.DAT`'s sixteen `LZH1` members
unpacking to 640×480 sheets.

Two measured answers rather than absences: **`ICONS.DAT` carries no `MMAP`
member at all** (21 unclassified members), and **`UIS_MCFL.DAT`'s 1,188
members** store their pixels under EA codec 4, `IPU1`, which nothing here
decodes — refused by name at both ends, read and write [M]. A further 162
images across the UI containers declare a pixel layout the decoder does not
implement, 140 of them in `LOADDATA.DAT` [M]. `UIS_PLYR.DAT` is listed last so
its 3,286 portraits do not fill the target list ahead of every other menu
texture; it is also on §3.2.2, which is where a player portrait belongs.

Bounding, caches and verifier are §3.1's — with one difference this page is the
only one to exercise: most `UIS_*.DAT` are plain `DATA` containers with **no
codec table**, so a replacement there can only be **stored**, and it must fit
the slot the member already owns or be refused.

**Real-disc proof** [M]: `UIS_TMLO.DAT:1:0`, 64×64, replaced with a synthetic
own-CLUT PNG — **stored**, 5,228 → 5,228 bytes, fitting the 5,248-byte slot the
member already owned, so **the container's directory did not move**. The
member is itself carried in `GAME.QKL`, so **the member's own cache copy was
rewritten**, 5,228 bytes at offset 4,297,664 — the other coherence path, on
real bytes. **4 ranges / 12,740,133 bytes declared**, image length unchanged,
verifier PASS with 284 untouched members byte-identical, 5 cache copies
re-read, **4,096 / 4,096 pixels exact, maximum channel error 0**.

**What still needs a boot.** `UIS_TMLO.DAT` member 1 came from the
Vikings-versus-Bears coin toss, where it shares its pixels with one other
texture [M]. It is the one edit that proves the **member-copy cache rewrite**:
if the game preloads the stale copy, the old texture appears and the edit is
silently ignored. And the negative that matters — a directory rewritten in
three cached copies is the step most likely to hang a preload rather than draw
the wrong picture, so a disc that boots to the menu and starts a game is the
evidence. Lane document:
[`MADDEN09_PS2_ART_PAGES.md`](MADDEN09_PS2_ART_PAGES.md).

### 3.7 Menus & UI — the text banks

`menus.text_members`, **`offline-writer-proved`**. Finds every `TEXT` member — a
member whose decompressed bytes are printable strings separated by NULs —
measures it (string count, longest and mean length, printable ratio, and the
SHA-256 of the decompressed bytes) and rewrites its strings in place.

**Measured on the retail disc** [M]:

```
14,748 TEXT members · 14,748 strings (one per member) · 3,242,117 bytes
```

That member count is exactly the whole-disc census in
[`EA_TERF_FORMAT.md`](EA_TERF_FORMAT.md) §4, arrived at independently — this
lane walks all 101 readable containers rather than sampling, so the two numbers
agreeing is a real cross-check. Whole-disc walk: **about nine seconds** [M].

**One classifier change, worth 12 members.** `identify_member` calls a member
`TEXT` when its first 32 bytes are printable, which stops being true of a bank
this lane has shortened — two printable bytes and thirty NULs. `is_text_member`
therefore discounts the padding before asking, which on the retail disc finds
**14,760 banks and 17,822 strings** rather than 14,748; every one of the twelve
extra is a NUL-padded name string in `STADATA.DAT` that the stricter rule was
missing [M]. It changes nothing about what the shared reader calls a member;
the widened rule lives in this lane.

**The catalogue carries no string.** A catalogue holds names, offsets, lengths
and digests and never payload, because a catalogue is a file that can be
shipped. The strings are read from the *user's own image* on demand, through
`TextLane.preview` and the command line's `--preview`, and are never stored.

**Why it is fast.** A member has to be unpacked before it can be classified,
but only its **first 32 bytes** — which is all `identify_member` looks at, and
where the codec stops. Only a member that matches is then unpacked in full.
Classifying by full decompression instead ran for over ten minutes on the
retail disc and was abandoned: 36,195 members, 4,269 of them `LZH1` streams
decoded in pure Python, for an answer the head already gave.

**How the write is bounded: a string slot.** One run of characters inside a
member, addressed by its **byte offset** rather than by its position in a
split, because an edit changes how a split comes out and an offset does not.
Its *allocation* is the room up to the next string — the NUL padding a previous
edit left included — so shortening a string does not spend it: the same room is
offered next time. A shorter replacement is padded with the format's
terminator; a longer one is refused with the length it has to fit. The member
keeps its exact byte count, so the container does, so the ISO extent does. On
this disc a bank is usually **one string with no NUL in it**, so its slot is the
whole member and replacing it replaces the whole bank; the label shows the
whole (elided) text and the budget shows the whole allocation, so what is being
replaced is on screen. A finer unit — the pipe-delimited `KEY=value` pairs
`OSDKSTRN.DAT` carries, say — would need that inner grammar decoded, and it has
not been. **Six of the eight containers are editable**: `GAMEDATA.DAT`,
`LOADDATA.DAT` and `STADATA.DAT` are named in the preload caches and refused
for §3.2.1's reason; `OSDKSTRN.DAT`, `STORYMSG.DAT`, `STRYCPTN.DAT`,
`STRYEMAL.DAT`, `STRYHDLN.DAT` and `STRYTEXT.DAT` are named in neither [M].

**What the verifier checks.** The image-level claim through
`ps2_iso9660_verify`, then the replaced slot re-read out of the destination's
own container and member, then the padding rule re-expressed rather than
borrowed: a writer that stopped padding and left the previous string's tail
behind fails even though the new value reads back.

**Real-disc proof** [M]: `OSDKSTRN.DAT` member 0, the slot at byte 0 — a
50,519-byte allocation rewritten with 37 bytes and padded with terminators —
**741,088 bytes declared in two ranges**, a 1,657,339,904-byte destination
built in 65 s, verifier PASS with **1,656,598,816 unchanged bytes** compared
across 197 entries (§7a).

**What still needs a boot.** The replaced string appearing on the screen that
draws it.

### 3.8 The Crib

No lane, by design. See §4.

### 3.9 Audio — the `SCHl` streams and the `BNKl` banks

Two rows over the six audio containers of the disc. Format:
[`EA_SCHL_FORMAT.md`](EA_SCHL_FORMAT.md); lane document:
[`MADDEN09_PS2_AUDIO.md`](MADDEN09_PS2_AUDIO.md).

**The catalogue** walks the six containers through a memory map and reads
headers only — no sound is decoded to list it. On the retail disc: **11,389
members, 34,046 streams, in 13.4 seconds**; the 301 banks and their 967 sounds
cost another **0.07 s** [M]. Each sound is listed with its container, member,
stream index, duration, sample rate, channel count and codec.

**`audio.streams`, `offline-writer-proved`.** **295 of the 34,046 streams are
EA-XA ADPCM — every stream of `BGM.DAT` and of `SOUNDDAT.DAT` — and 289 of them
decode**, the six that declare no sample rate being listed and refused rather
than exported at an invented rate [M]. A decoded sound is 16-bit PCM in a plain
RIFF/WAVE file. **The other 33,751 streams are EA MicroTalk** (header codec 4)
— every line of speech and commentary on the disc — and are refused by name in
their own row (§4).

*How the write is bounded.* A WAV is mixed to the sound's channel count and
resampled to its rate **by linear interpolation** — plainly, on the page —
re-encoded as EA-XA ADPCM, and it **must fit the bytes the sound already
occupies**. The check is arithmetic, not a trial encode: EA-XA's frame is a
fixed 15 bytes for 28 samples, so the encoded size is known the moment the WAV
is chosen; a longer one is refused naming the byte count it had to fit and
roughly how many seconds do fit. The new stream is written into the member's
own bytes and the remainder of the member's stored length is zero-filled —
the shape the disc already has between two streams in one member [M]. Nothing
moves: the `TERF` header, the `DIR1` directory and every other member come
through unchanged, and the build checks that rather than assuming it. **The
caches are rewritten rather than refused:** every copy of a changed member is
rewritten with it and the `.QKL` becomes another same-size replacement with its
own declared range; copies are deduplicated, so an offset an untouched member
also points at is **refused**. On the retail disc that rewrite fires on
nothing, and that is measured: `BGM.DAT` has no member copies, and of
`SOUNDDAT.DAT`'s 43 carried members not one is among its 119 stream members
[M]. The path is here because the measurement could have gone the other way;
CI proves it on a synthetic cache that *does* carry a replaced member.

*What the verifier checks.* Four things, importing neither the writer nor
anything of the receipt beyond the ranges it declares: a destination whose
length differs from the source is refused; both images are streamed a megabyte
at a time and the **first** differing byte outside every declared range fails
it; the destination is re-opened as a disc in its own right, each replaced
sound found **by key**, decoded and compared with the user's own WAV — resampled
and mixed the same way the build did — refusing below **30 dB** SNR; and the
preload copies are re-derived **from the destination's own caches**, failing on
a stale member or header copy.

*Real-disc proof* [M]: one `BGM.DAT` stream replaced by a ten-second computed
tone — 122.5 s to build, **1,657,339,904 bytes in and out**, verify **PASS at
47.4 dB**, 2 declared ranges, 1 preload copy checked; the destination was
deleted immediately after the verdict.

**`audio.banks`, `extract-only`.** All 967 bank sounds are Sony PlayStation
ADPCM and the 508 that declare a sample rate decode and export [M]; nothing is
written to the disc. §4 says why the writer is not offered.

**What still needs a boot.** Load a rebuilt image in PCSX2 and hear the
replaced track. That is the only thing between the streams row and
`runtime-proved`.

### 3.10 Gameplay — the executable patches

`gameplay.executable_patches`, **`offline-writer-proved`**. One host patch is
translated, `playbook_editor_caps`: four parameters drive **five `sltiu`
immediates** in `SLUS_217.70` — the formation, set, play and plays-per-set caps
of the in-game create-a-playbook editor (20 / 20 / 100 / 60 as shipped). Each
site is one instruction of the form `count + n < IMM`, so the cap is `IMM − 1`
and the translation changes **only the low 16 bits**:
`replacement = (original & 0xFFFF0000) | ((cap + 1) & 0xFFFF)`. `sets_cap`
drives two words because the editor's `room_for_formation` predicate tests
PBFM, PBST and SETL in one conjunction [M].

**How the write is bounded.** Every original word is re-read from the user's
own executable at plan time and must match. A cap below the one the executable
already enforces is refused, and one above 65534 is refused because `cap + 1`
would not fit the immediate; `sltiu` sign-extends, so from 32767 up the site
stops being a cap at all — allowed, because that is how a user removes the
check, and the emitted pnach's own comment says which happened. Delivery is a
PCSX2 / PenguinScreen2 `.pnach` by default, or the five words written into the
boot ELF on a **new** image through the shared fixed-allocation ISO9660 writer;
a word replacement never changes the executable's length, so nothing moves and
the build declares exactly `4 × (words written)` bytes — the tightest claim
available.

**What the verifier checks.** For the pnach: it re-parses the file, re-opens
the user's image, re-reads every original word, and fails if the file names a
different CRC, declares an address the receipt does not, misses one, writes a
different word, or carries a disabled line. For the disc route it imports none
of the writer: it re-opens the **destination**, pulls its boot ELF out
independently, checks each declared word holds its replacement and that the
source held the original, checks **every other byte of the executable** is
unchanged, and streams both whole images failing on any differing byte outside
a declared four-byte range.

**Real-disc proof** [M]: the five original words were read out of the owner's
own retail *and* Deluxe executables and decoded with a disassembler written for
this task; the two editions differ in exactly nine 32-bit words and **none of
the nine is at a translated site**, so one recipe translates identically on
either disc. Writing the four-cap recipe into the retail image on the disc
route moves the PCSX2 game CRC from `38014255` to `380143EF` — measured, and
the reason the two delivery routes should not be stacked.

**What still needs a boot.** Load a shipped 20-set playbook in the
create-a-playbook editor with the pnach active and try to add a 21st set;
recording the message that appears is the whole result. The prediction for what
stops it next — the library's own insert guard returning status 19 — is
written as a prediction, not as evidence. Lane document:
[`MADDEN09_PS2_CODE_PATCHES.md`](MADDEN09_PS2_CODE_PATCHES.md), which carries
the per-site disassembly, the retail/Deluxe word table, and §4's reason the
runtime capacity layer is not shipped.

### 3.11 Playbooks & Plays — the 102 shipped books

`playbooks.databases`, **`offline-writer-proved`**. The 102 shipped playbooks
are EA TDB databases packed as `LZH1` members 0–101 of `/DATA/GAMEDATA.DAT`
(115 members, 104 of them databases; the two beside the books are the in-game
route menus) [M].

**Why this page did not exist until now.** Every one of those databases
declares a table named **`SGF` followed by a NUL byte**, and the reader decoded
a four-character name as strict printable ASCII, so **103 of the disc's 355
databases were refused before a row was read**. `ea_tdb.decode_name` /
`encode_name` now treat a name as four **bytes**, rendering a byte outside
`0x20..0x7E` as `\xNN` and a literal backslash as `\\` — a bijection, so no two
names collide — and the reader still refuses a name with no printable byte at
all. The result, read-only, over the whole retail disc [M]: **355 databases
parse where 252 did, 0 refused, 4,108 tables, 85,400 field definitions, and
8,926 checksum sites with 0 wrong** where 4,806 were checked before. Across all
89,508 table and field names on the disc the **only** byte outside
`0x20..0x7E` anywhere is that one trailing NUL, and no name carries a backslash
[M] — so the escape is a safety property rather than something the corpus
exercises.

**What the page edits.** The `name` field of the eight tables that carry one —
`FORM` 1,000 rows, `PBFM` 919, `PBST` 2,300, `SETL` 2,402, `SGF\x00` 17,630,
`PBPL` 22,105, `PLYL` 22,103, `SPKF` 8,992 — plus **six numeric fields, each
with a source**: `FORM.FTYP`, `PBFM.FTYP` and `PBAU.FTYP` (the formation-type
enum), `PBAU.PBAU`, `PLYL.risk` and `PLYL.motn`. Widths are read out of each
file's own field directory. That is **102 book targets, 1,938 table targets and
78,875 editable row targets**, catalogued in 32 s at 129 MB peak RSS [M].
Everything else is deliberately not offered: foreign keys into the play graph,
`ARTL`'s route points, `PBAI`'s AI weights and `PSAL`'s step chains. A renamed
play is a bounded change; a re-pointed foreign key is a dangling reference
nobody has booted. **No row is added or removed** — every table in every
shipped book has `record_count == max_records`, **1,938 of 1,938** across the
102 books and 1,944 of 1,944 across all 104 `GAMEDATA.DAT` databases [M]. **A
book has no name of its own** on this disc, measured in three places, so a
target is labelled by the member it is.

**How the write is bounded: two paths, and which one the disc takes.** A record
edit never changes a database's length, so the only thing that can move the
container's directory is the size of the re-encoded `LZH1` member. On the
**exact-size** path the member is re-encoded under a byte budget equal to the
bytes it already occupies, padded with NULs to exactly that size and spliced in
place: every directory word is unchanged by construction, no other member
moves, and the caches' copies of the directory stay correct without being
touched. Padding is safe because a bounded decode stops as soon as it has
produced the declared number of bytes — measured, not assumed: **all 102
shipped books padded to EA's stored size decode back byte-identical** [M], and
the writer re-decodes every stream it pads before it splices it. On the
**growth** path `plan_member_rewrite` chooses the codec, `rewrite_member` lays
the container out again, and both of `FE.QKL`'s directory copies are rewritten
with it. Headroom, measured on every shipped book: **102 of 102 fit their own
slot**, smallest headroom **263 bytes**, largest 4,023, our bytes 0.938–0.958
of EA's [M] — the ordinary case by a wide margin, but not guaranteed, which is
why the growth path exists and the receipt names which path each member took.
**The cache rule here is member-level, not container-level:** `GAMEDATA.DAT` is
named in both caches, so §3.2.1's container-level refusal would refuse every
playbook. `GAME.QKL` carries byte copies of **members 103–112** and no
directory; `FE.QKL` carries **two copies of the directory** and no members [M].
**No playbook is cached**, which is what makes members 0–101 writable at all,
and a member that *is* cached is refused by name.

**What the verifier checks.** Six things, trusting the receipt for none of
them: the destination is the source outside the declared ranges and no
untouched extent moved; every edited value reads back out of the destination's
own container, member, table, record and field; every differing byte inside an
edited database lies in a declared field span or a checksum slot; all four
kinds of TDB checksum agree; every member the recipe did not name is
byte-identical and still packed; and every copy a preload cache carries of the
container still equals what it copies, re-read from the destination.

**Real-disc proof** [M]: `GAMEDATA.DAT` member 67 — the deepest shipped book,
346 plays over 13 formations — `SETL` record 0, the name field, on the
**exact-size** path: EA's 67,149 stored bytes against our 63,166 plus 3,983
NULs, **container directory unchanged, 0 preload caches rewritten**, two
declared ranges, destination **1,657,339,904 bytes — the same as the source**,
and the verifier passing with 1 value read back, **40 checksum slots all
correct**, **114 untouched members byte-identical**, **12 preload-cache copies
still equal to what they copy**, 0 undeclared changed bytes, and 1,652,917,496
unchanged bytes compared.

**What still needs a boot.** The owner opens the edited playbook in-game and
reads the renamed set; that the rest of the book still works; that the game's
own decoder ignores the padding as ours does — an inference [A], and the
load-bearing assumption of the ordinary path; and, if an edit ever takes the
growth path, that the game still loads after `FE.QKL`'s directory copies have
been rewritten. Lane document:
[`MADDEN09_PS2_PLAYBOOKS.md`](MADDEN09_PS2_PLAYBOOKS.md).

### 3.12 All Textures — the container inventory

`textures.container_inventory`, **`read-only-mapped`**. Walks every `/DATA`
file, opens the ones that are containers, and lists them: chunk chain,
alignment, member count, codec histogram, and per-member offset, stored size,
codec, unpacked size and post-decompression format.

**Measured on the retail disc** [M]:

```
101 containers (of 107; six are over the 96 MB read limit)
36,195 members
codecs: 0 (stored) and 5 (LZH1) only
formats (first 256 members of each container, 9,063 classified):
  MMAP 4,901 · TEXT 1,288 · unclassified 764 · SMF 626 · TERF 500
  TDB 354 · DMF 300 · SCHl 167 · empty 137 · FNTS 14 · SKL1 8 · SEVT 3 · ELF 1
```

The format histogram samples the **first 256 members of each container**, and
every row records how many it sampled, so the numbers are never read as a
whole-container census. That is a speed decision — unpacking 36,195 `LZH1`
streams in pure Python is not free — not a format limit; the whole-disc census
is in [`EA_TERF_FORMAT.md`](EA_TERF_FORMAT.md) §4. Whole-disc walk: **about ten
seconds** [M]. The lane caps its *target list* at 4,000 rows because a table is
a table and 36,195 rows is a data dump; the document's counts stay complete
either way.

Nothing is written, so there is nothing to bound and no boot to wait for. The
verifier's job here is the reader's own: the shared `TERF` reader is proved on
synthetic containers at every alignment and both chunk kinds, and a container
that does not obey the layout rules is listed with its size, unread, rather
than half-parsed.

### 3.13 Saves

No lane, by design. See §4.

### 3.14 Build & Share

The shell's own page, core-owned, and the one page no game module writes. It
chains the staged edits of every other page into a new image through child
processes, keeps each step's receipt, and runs each lane's own verifier between
steps. Madden 09 contributes nothing to it but lanes.

---

## 4. Pages that state a reason instead of a lane

Two of the fourteen. Each has one sentence in `game.json`'s `page_notes`, shown
under the shell's own; both are **by design**, not "not built yet".

- **The Crib** — *The Crib is an ESPN NFL 2K5 feature and not a Madden concept,
  so this page stays empty here on purpose.*
- **Saves** — *A Madden 09 memory-card save is a different repository's
  tooling; this studio works off the disc, so nothing here reads or writes a
  save.* This is a scope boundary rather than a measured impossibility, and §10
  says so.

The other twelve pages carry a lane or, for Build & Share, the shell's own
page. What they still refuse, they refuse **inside** a page that works, and
each refusal is a measurement rather than a gap:

- **`SMF` and `DMF` geometry is listed and never opened.** 805 `SMF` and 2
  `DMF` members in the two stadium containers and 642 `SMF` in `FIELDART.DAT`
  [M] — a stadium's shape, its stands, its scoreboard mesh, its crowd, and nine
  in ten of the field-art file. No decoder for either format is built anywhere
  in this repository and no layout for either is documented here, so the
  catalogue counts them by format per container and §3.4 / §3.5 leave them
  alone.
- **`IPU1` pixels are refused by name.** All 1,188 members of `UIS_MCFL.DAT`
  store their pixels under EA codec 4; all that is known of it is the run's own
  header [M]. They are listed and refused at both ends, read and write, never
  exported wrong. "IPU1 is the PS2 MPEG intra unit" is a guess from the codec's
  name, not a measurement [A].
- **MicroTalk speech is listed and not decoded.** 33,751 of the disc's 34,046
  streams are EA MicroTalk — every line of speech and commentary [M]. ffmpeg
  carries no decoder for it and refuses it by name, so a decoder written here
  could not be checked against anything. Their rate, channels and length are
  read from the disc; their audio is not.
- **The bank writer is not offered.** The PS ADPCM encoder exists and
  round-trips a computed tone at 57 dB, so it is not the codec that stops it:
  **134 of the 967 bank sounds carry loop points** (tags `0x86`, `0x87`,
  `0x89`) whose meaning this module has not established [M], the PlayStation
  SPU plays a bank sound from parameters nobody here has mapped [A], and no
  rebuilt container has been booted. Replacing a looped sound without knowing
  what the loop tags address is how a sound effect ends up stuttering in a game
  nobody here has run. `check_edit` refuses every value with that sentence.
- **The scorebug is drawn by the executable.** The scorebug and the broadcast
  overlays are drawn from values the executable holds, not from a data file,
  and nothing on this disc has been mapped to them. §3.6 edits the art those
  screens draw and says this in the same breath, because the page having
  nothing was the part that was wrong.
- **`TEMPLATE.DAT`'s third identity copy is refused.** It carries a
  **byte-identical third copy** of all 32 teams' identity fields [M], and it is
  not written, because `TEMPLATE.DAT` is named in `/DATA/FE.QKL`, which carries
  a copy of at least some of what it names [M][S]. A team renamed by §3.3 is
  renamed in two of the three databases that carry its identity and not the
  third; **which copy any given screen reads is not established** [A], so no
  claim either way is made and a screen still showing the old name is the first
  thing a boot should be watched for. The same file is why a full **relocation**
  is out of scope: a team's stadium (`STAD`) and city name (`CITY`) exist only
  in `TEMPLATE.DAT` members [S], so this page renames and recolours a team where
  it plays; it does not move it.
- **The playbook capacity layer is measured and not shipped.** §3.10's five
  words are the editor-side check only; the runtime capacity comes from the
  table header the disc packed exactly full, and raising it needs new code that
  only a boot could verify. §7 keeps the claim.

---

## 5. What is measured, in one table

Every number this module quotes about a real disc, and the document that
carries it. All read-only; nothing was written to either image except the
scratch destinations of the real-disc trials, each deleted immediately after
its verdict.

**The discs and the containers**

| number | value | source |
|---|---|---|
| retail image bytes | 1,657,339,904 | §1 [M] |
| Deluxe image bytes | 1,846,476,800 | §1 [M] |
| `/DATA` files that differ between the two | 13 | §1 [M] |
| containers read | 101 of 107 (six over the 96 MB cap) | §3.12 [M] |
| members in them | 36,195 | §3.12 [M] |
| members classified (256/container sample) | 9,063 | §3.12 [M] |
| inventory walk | ~10 s | §3.12 [M] |
| preload-cache copies read, all identical to what they copy | **6,270 across 39 containers** | §3.1, `EA_TERF_FORMAT.md` §9 [M] |
| the same, over the seven audio containers | 5,805, 0 differing | `MADDEN09_PS2_AUDIO.md` §3 [M] |

**The databases**

| number | value | source |
|---|---|---|
| TDB databases parsed | **355 of 355**, 0 refused | `MADDEN09_PS2_PLAYBOOKS.md` §1 [M] |
| — before the four-byte name fix | 252, 103 refused | same [M] |
| tables · field definitions | 4,108 · 85,400 | same [M] |
| checksum sites verified | **8,926**, **0 mismatches** | same [M] |
| — the pass before the name fix | 4,806 across 252 databases, 0 mismatches | §3.2.1 [M] |
| tables · records · field definitions, as the pre-fix reader counted them | 2,151 · 354,812 · 60,537 | §3.2.1 [M] |
| team-data walk · catalogue with rows | ~19 s · ~29 s | §3.2.1 [M] |
| editable roster rows (`DB_TEAMS.DAT`) | 12,499 | §3.2.1 [M] |
| teams listed · rows one recipe writes | 32 · 64 | `MADDEN09_PS2_IDENTITY.md` §3.1 [M] |
| copies of a team's identity on the disc · written | 3 · 2 | `MADDEN09_PS2_IDENTITY.md` §2 [M] |
| `TEXT` members carrying a team's identity string | 543 of 14,748 (464 five characters or longer) | same §2.3 [M] |

**The playbooks**

| number | value | source |
|---|---|---|
| shipped books · tables · editable rows | 102 · 1,938 · 78,875 | `MADDEN09_PS2_PLAYBOOKS.md` §2.5 [M] |
| tables packed exactly full | **1,938 of 1,938** (1,944 of 1,944 across all 104 `GAMEDATA.DAT` databases) | same §2.3 [M] |
| records in the 102 books | 670,263 | same §1 [M] |
| books whose re-encode fits its own slot | **102 of 102**; smallest headroom 263 bytes | same §3 [M] |
| padded streams that decode back identical | 102 of 102 | same §3 [M] |
| catalogue | 32 s, 129 MB peak RSS | same §2.5 [M] |

**The text banks**

| number | value | source |
|---|---|---|
| `TEXT` members (shared reader's rule) | 14,748 · 14,748 strings · 3,242,117 bytes | §3.7 [M] |
| `TEXT` banks (this lane's widened rule) | 14,760 · 17,822 strings | §3.7 [M] |
| text walk | ~9 s | §3.7 [M] |

**The art**

| number | value | source |
|---|---|---|
| texture members, four uniform containers | 1,780 · 7,616 images · 7,082 decodable · 534 refused | §3.1 [M] |
| texture members, four art pages | 12,876 · 13,140 images · 11,735 decodable | `MADDEN09_PS2_ART_PAGES.md` §3 [M] |
| — distinct images among them (`UIS_PLYR.DAT` is on two pages) | 8,449 | same §1 [M] |
| — stadiums · field art · presentation · faces | 514 · 73 · 7,678 · 4,611 members | same §1 [M] |
| `MMAP` members that rebuild byte for byte from their own pixels | **1,780 of 1,780** | §3.1 [M] |
| `LZH1` members that re-encode and decode back byte for byte | **1,836 of 1,836**, aggregate 1.0078× EA's | `EA_TERF_FORMAT.md` §5.3 [M] |
| catalogue cost: uniforms · stadiums · field art · presentation · faces | ~4 min · 7.5 s · 4.7 s · 19.3 s · 41.8 s | §3.1, `MADDEN09_PS2_ART_PAGES.md` §3 [M] |
| PCSX2 replacement identities, uniform lane's containers | **3,024** disc textures, from 27,873 surfaces indexed and 9,617 unique dumped names | §6.5 [M] |
| PCSX2 replacement identities, the four art pages | **234 of 8,449** distinct textures | `MADDEN09_PS2_ART_PAGES.md` §4 [M] |
| frames in the capture both tables were learned from | **33** | §6.5 [M] |

**The audio**

| number | value | source |
|---|---|---|
| members · streams · banks · bank sounds | 11,389 · 34,046 · 301 · 967 | `MADDEN09_PS2_AUDIO.md` §1, §8 [M] |
| streams by codec | 295 EA-XA (289 decode; 6 declare no rate) · **33,751 MicroTalk, refused** | same §2, §9 [M] |
| bank sounds that declare a rate and decode | 508 of 967 | same §2 [M] |
| bank sounds carrying loop points | 134 | same §5 [M] |
| decoder agreement with ffmpeg, streams | **289 of 289 byte-identical**, 670,692,008 PCM samples | same §8 [M] |
| decoder agreement with ffmpeg, bank sounds | **508 of 508 byte-identical**, 33,451,124 PCM samples | same §8 [M] |
| catalogue | 13.4 s (+0.07 s for the banks) | same §1 [M] |

**The executable**

| number | value | source |
|---|---|---|
| retail · Deluxe boot ELF PCSX2 CRC | `38014255` · `084562FF` | §3.10 [M] |
| words the two executables differ in | 9, **none at a translated site** | `MADDEN09_PS2_CODE_PATCHES.md` §2.7 [M] |
| editor-cap words translated | **5** (four parameters) | same §1 [M] |
| community patch entries for either CRC | **0** of PCSX2's 4,471 | same §3 [M] |

And the same three read-only lanes on the **Deluxe** disc [M], which is the
point of telling the two apart:

| number | retail | Deluxe |
|---|---|---|
| containers read | 101 | 100 |
| members | 36,195 | 34,600 |
| `MMAP` in the sample | 4,901 | 4,647 |
| `SMF` in the sample | 626 | 398 |
| TDB databases | 355 | 355 |
| TDB records | 354,812 | **340,806** |
| TDB field definitions | 60,537 | **60,569** |
| `TEXT` members | 14,748 | 14,748 |

The Deluxe team rewrote the databases and the geometry containers and left the
text banks alone, and the lanes say so without being told. Those are the
team-data lane's counts as it reported them on each disc **before** the
four-byte-name fix widened what parses, which is why the record and field
totals are the smaller pair; both columns were read the same way, which is what
makes the comparison mean something.

Reproduce any of them — every lane runs from the command line with no window:

```
python3 -m mod_editor.games.madden09_ps2.inventory_lane  --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.team_data       --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.text_lane       --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.identity_lane   --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.playbooks_lane  --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.audio_lane      --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.uniform_art     --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.art_pages       --source "<your>.iso" --page stadiums
python3 -m mod_editor.games.madden09_ps2.code_patches    --source "<your>.iso"
```

A writing lane takes the same command one step further — a recipe in, a NEW
image out, and the independent verifier's verdict printed:

```
python3 -m mod_editor.games.madden09_ps2.team_data --source "<your>.iso" \
    --recipe edits.json --destination new.iso --report receipt.json
python3 -m mod_editor.games lane madden09_ps2 stadiums.textures build \
    --source "<your>.iso" --destination NEW.iso --recipe recipe.json \
    --catalogue catalogue.json --receipt receipt.json
```

Every one of them also runs with no disc at all — `--selftest`, or the ten
validators — because each lane builds its own synthetic source.

---

## 6. The `MMAP` verdict

**PROVED for version 2. NOT PROVED for version 1.**

### 6.1 Why it looked undecodable

`MMAP` was read as a header followed by a bitmap, and it is not. It is a
**table-of-tables**: a 40-byte section directory, then an image table, a
surface table (one row per mip level), a palette table and a name table. An
earlier census of these bytes recorded "three ascending `u32` sizes" at
`+0x1C`/`+0x20`/`+0x24` and "`u16` width, `u16` height at `+0x28`". Both
observations were correct about the bytes and wrong about what they are: those
three are the palette, name and attachment tables' **offsets**, and the width
and height are the **first surface row's** first four bytes.

That correction is what unlocked it. The full layout is in the module
docstring of `mod_editor/games/madden09_ps2/mmap_art.py`.

### 6.2 The rules that had to be right

Each of these silently corrupts every texture, so each has a test:

1. **A surface's format word is two halves** — the low 16 bits are the pixel
   layout (0 = 4-bit indexed, 1 = 8-bit indexed) and the high 16 bits are the
   **EA codec its pixel run is packed under**, using the same ids `ea_terf`
   already names. So a texture can be compressed *inside* a member the
   container has already unpacked.
2. **A 256-entry CLUT is CSM1-interleaved** and must be de-interleaved; a
   16-entry one must not be touched.
3. **Alpha is 0..128**, not 0..255, with `0x80` fully opaque.
4. **Level 0 is the base**, always. One member of the retail disc stores its
   remaining levels out of order, so "the last one" is not the same thing [M].
5. **A prefix will not do.** Only the surface table is at the front.

### 6.3 The evidence

Not "the sizes add up". The exported PNGs were **looked at**:

- `PLYRFACE` members decode to recognisable human face textures — eyes with
  irises, nostrils, a mouth, a beard, correct skin tones, with the eyebrow
  sprite strip and teeth strip an EA face atlas carries.
- `COACFACE` — twelve distinct coach faces, several with moustaches, from
  `LZH1`-compressed members. So the rule works straight through the container
  codec.
- `UNIFORMS` — a white jersey with red and blue trim (sleeves, collar,
  shoulder pads, stitching); the jersey-number font sheet, digits legible; and
  a 1491x32 name-plate strip carrying a fully legible alphabet, which is also
  what proves the stride rule at a width that is not a power of two.
- `TATTOOS` — kanji, tribal designs, a koi fish, gothic capitals.
- `UIS_PLYR` / `UIS_LOAD` — player portraits including dreadlocks, and
  photographic loading screens with readable jersey numbers.

And the two failure modes are visible, which is what makes the positive result
mean something: a wrong stride shears the image diagonally, and a 256-entry
palette left interleaved gives a recognisable face **speckled with wrong
colours**. The same member decoded both ways, side by side, is what settled
the de-interleave.

Two implementations agree: the one in this module and an independent one
written from the same measurements, byte-identical on every member compared.

### 6.4 What stays unknown

- **`IPU1` is not decoded.** All 1,188 version-1 members of `UIS_MCFL.DAT`
  pack their pixels under EA codec 4; all that is known of it is the run's own
  header. They are refused by name, never exported wrong. "IPU1 is the PS2
  MPEG intra unit" is a guess from the codec's name, not a measurement [A].
- **Which alternate CLUT the game picks for a team is not established** [A].
  A uniform member carries up to 18 of them; the decoder takes the image's
  first and says so.
- **Pixel layouts 3 and 4 exist and are not proved** — four `GAMEDATA`
  surfaces and every `UIS_MCFL` one. Only 0 and 1 are decoded.
- **The `00 01 02 03` marker at `+0x08` means nothing yet** [A].
- **Nothing was checked in PCSX2.** The evidence is "the PNG is recognisable
  art", not "the game renders it identically". That is the same gap that
  stops the pack writer, and §7 keeps it.

### 6.5 The PCSX2 replacement identity, learned from a real dump [M]

A replacement filename is `<tex0 hash>-<clut hash>-<bits>.png`, and the two
hashes are XXH3-64 over the GS's own texture and CLUT memory: **no disc file
carries them**. `tools/madden09_ps2_texture_identities.py` learns the mapping
instead — it decodes every `MMAP` surface on the disc, decodes every PNG a
PCSX2 dump wrote, and pairs them on **exact pixel equality**, no tolerance,
because two textures that differ by a byte are two textures.

Two details make the equality exact rather than approximate:

* **PCSX2 dumps the CLUT's own alpha**, 0..128 as the PS2 stores it, not
  rescaled to 0..255 — the alpha histogram across the dump peaks at 128 and
  reaches 155, which a 0..255 rescale cannot produce [M]. `decode_rgba` grew a
  `raw_alpha` flag for exactly this caller.
* **A texture is dumped once per naming convention** — `ClassicTextureNames`
  carries TCC in bit 14 of the `bits` word and stock PCSX2 drops it — so both
  names are kept and `replacement_identity` prefers the classic one, which
  every build parses.

**The corpus**: 33 frames replayed from GS dumps of the retail disc through
`pcsx2-gsrunner` — one pre-game captains frame and 32 coin-toss screens
covering the coloured and the white kit of all 32 teams. 17,688 files,
**9,617 unique names** after the same texture in two frames is counted once.

| | |
|---|---:|
| disc surfaces indexed (7 containers) | 27,873 |
| dump files matched to exactly one disc texture | 2,678 |
| dump files matching more than one (a picture members share) | 1,637 |
| dump files agreeing on RGB and not on alpha | 744 |
| dump files unmatched | 6,195 |
| — of those, region dumps (`-r<W>x<H>`, a sub-rectangle) | 3,502 |
| **disc textures given an identity** | **3,024** |

By container: `UNIFORMS.DAT` 2,797, `STADIUMS.DAT` 76, `UIS_TMLO.DAT` 58
(team logos), `PLYRFACE.DAT` 45, `FIELDART.DAT` 32, `UIS_COMN.DAT` 10,
`UIS_IG.DAT` 6.

**Which team a member belongs to is still not in the file — but it is in the
capture** [M/A]. `UNIFORMS.DAT` names nothing; each frame shows exactly two
teams, one in colour and one in white, so a texture belongs to whatever team
is in *every* frame that drew it. Of the 2,797 identified uniform textures:
**62 are attributed to one team**, 1,808 narrow to one matchup and no further,
and 927 are drawn in more than one matchup and are not a kit at all.

The 62 are the check that the method works rather than a disappointment: they
are **Giants and Patriots only**, and those are exactly the two teams that
appear in *three* frames — their own coin toss plus the captains frame — so
they are the only two whose frame sets intersect down to one team. Every other
team plays one matchup, and one matchup cannot say whether a texture is the
coloured side's or the white side's. A third frame per team would close it,
and the tool needs no change to use one.

**What this does not prove.** It records the names PCSX2 *wrote while
dumping*. Nothing here has loaded a replacement pack, so the *Write PCSX2
pack* step stays unoffered. The identity is also learned rather than derived:
the CLUT half of the name **does** reproduce from the disc — XXH3-64 over the
de-interleaved CLUT reproduces the dumped `clut` field exactly on every pair
checked [M] — and the TEX0 half does not yet, so the durable
compute-it-from-the-bytes route is half open and the pixel matcher is what
works today.

---

## 7. What this module does not claim

Said plainly, because a page that stays quiet about its limits is worse than
one with fewer pages.

1. **Nothing has been booted.** Eleven rows write — the team databases, the
   team identity, the text banks, the uniform art, the faces, the stadium art,
   the field art, the UI art, the audio streams, the playbooks and the
   executable patches — and every one of them is `offline-writer-proved`, which
   is as high as a claim can go from this box. Two rows are `extract-only`
   (`uniforms.mmap_export`, whose writer is a separate row at a higher rung;
   `audio.banks`, for the reason in §4) and one is `read-only-mapped`
   (`textures.container_inventory`, which writes nothing at all). The honest
   next test is: rebuild a container, put it back in an ISO, boot it in PCSX2,
   see the game load it and see the change on a screen. **That has not been
   run.** Every claim in §3 is about bytes.
2. **MicroTalk is not decoded.** 33,751 of the disc's 34,046 streams are EA's
   speech codec, and no oracle exists anywhere in reach to check an
   implementation against — ffmpeg refuses it by name [M]. They are listed with
   their rate, channels and length; their audio is not read. Nor are the six
   EA-XA streams and 459 bank sounds that declare no sample rate: they are
   refused rather than exported at an invented one.
3. **The bank loop tags are not decoded**, which is what keeps `audio.banks` at
   `extract-only`: 134 of the 967 bank sounds carry tags `0x86` / `0x87` /
   `0x89` whose meaning is not established [M], and the SPU plays a bank sound
   from parameters nobody here has mapped [A].
4. **The playbook capacity layer is measured and not shipped.** §3.10's five
   words are the editor-side check only. `table_set_capacity` (`0x0082A6A0`) is
   a subroutine with **no number in it to raise**; five of its six static
   callers hand it the capacity they just read out of the table header, which
   the loader took from the disc, and every on-disc table is packed exactly
   full [M]. Raising it means new code in a cave, whose *correctness* would be
   pure assertion until a boot, and the hook site is recorded as located but
   not fully pinned [S]. So the expected behaviour of the shipped patch alone is
   that the editor stops refusing at 20 and starts being refused one layer
   lower with status 19 — **a prediction about unbooted code, written here as a
   prediction**.
5. **`SMF` and `DMF` geometry are identified and not decoded.** 805 `SMF` and
   2 `DMF` members in the stadium containers, 642 `SMF` in the field-art one,
   626 `SMF` in the whole-disc sample [M]. Knowing a member's magic is not the
   same as reading it, and the module does not blur the two. The same holds for
   `IPU1` pixels (§4).
6. **What the preload caches carry is measured; what the game does with a
   disagreement is not.** `GAME.QKL` and `FE.QKL` hold byte copies of container
   directories and of particular members — **6,270 copies across 39
   containers, every one compared identical to the disc** [M].
   `containers.preload_copies` names them, and every writer either keeps every
   copy in step or refuses the edit by name. **What the game does when a copy
   and its container disagree is not known and not tested**, and neither is
   *what* a cache carries of a file it names in general: `STADATA.DAT` is named
   in both and its head is in neither [A].
7. **The PCSX2 replacement identity is learned, never derived, and its coverage
   is what one capture reached.** A replacement filename is built from the GS
   TEX0 and CLUT hashes PCSX2 computes at draw time, and no disc file carries
   them; `tools/madden09_ps2_texture_identities.py` pairs a real texture dump
   with the disc **by pixels**. The corpus is **33 frames** — 32 coin-toss
   screens and one pre-game captains frame — so the table names **3,024** disc
   textures across the uniform lane's containers and **234 of the 8,449**
   distinct textures the four art pages cover, leaving 8,215 with `None` and a
   sentence saying why. Of the 2,797 identified uniform textures only **62 are
   attributed to one team**, and those are Giants and Patriots only, because
   they are the two teams that appear in three frames. **No pack built from
   these names has been loaded in an emulator**, so *Write PCSX2 pack* is not
   offered from any row: what is proved is the pairing. The CLUT half of the
   name does reproduce from the disc's own bytes; the TEX0 half does not yet.
8. **Every real-disc trial is on the retail disc.** The Deluxe image is
   identified, catalogued and compared (§5), and its executable was read
   word-for-word against the retail one (§3.10), but **nothing has been written
   into a Deluxe image** by any lane. The retail/Deluxe word table is why one
   recipe is *expected* to translate on either disc; it is not evidence that a
   rebuilt Deluxe container is sound.
9. **The container checksum question is open** [M/A]. No field in any container
   header varies with content in any way the reader could find, and the layout
   rules hold with zero residue across 47,769 members — but that is the whole of
   the search, and it is not proof. The circumstantial evidence is good (the
   community's Deluxe disc rewrites five containers, carries two defects the
   retail disc does not, and still plays [S]); it does not close the question.
10. **`PWGT` and `PHGT` have no units this module will label a control with.**
    `PWGT` looks like pounds less 160 on the records sampled [A], and "looks
    like" is not a unit, so height and weight are deliberately absent from
    §3.2.1's editable fields even though the fields are read and catalogued.

---

## 7a. The real-disc trial

The first two writers' trial, in full. Each of the other eight real-disc runs
is one line in its own subsection of §3 and in full in its lane document; this
one is kept whole because it is the one that established the shape every later
trial follows — read-only source, scratch destination, declared ranges, an
independent verdict, a negative control, and the destination deleted.

Run once, on the owner's own retail `SLUS-21770` image, opened read-only. Both
destinations were built in a scratch directory and **deleted immediately
afterwards**; nothing was written next to the disc.

**Team data.** Catalogue: 14,518 targets, 12,499 editable rows, 26 s. Edit:
`DB_TEAMS.DAT` member 0, `PLAY` record 0 — first name, last name and jersey
number. Declared **2,585,800 bytes in two ranges**: the container's whole
extent (2,585,792 bytes at 1,177,688,064) and its directory record's 8-byte
length field (at 538,410). Built a **1,657,339,904-byte** destination — the
source's exact size — in 89 s. The verifier passed: three values read back from
the destination's own container, all **44 checksum slots** of the edited
database correct, **0** bytes of the member changed outside a declared field
span or checksum slot, and `ps2_iso9660_verify` comparing **197 entries and
1,654,754,104 unchanged bytes**.

**Text.** Catalogue of that built image: 14,760 banks, 17,822 strings, 4 s.
Edit: `OSDKSTRN.DAT` member 0, the slot at byte 0 — a 50,519-byte allocation
rewritten with 37 bytes and padded with terminators. Declared **741,088 bytes
in two ranges**. Built a 1,657,339,904-byte destination in 65 s; the verifier
passed with **1,656,598,816 unchanged bytes** compared across 197 entries.

**The negative control.** One byte at offset 1,657,339,903 — outside every
declared range — was flipped, and the same verifier **failed**, naming the
offset. Putting the byte back made it pass again.

Read back out of the final image with the plain readers, not the writers:
the edited `PLAY` record's names and jersey number are the new ones, its
overall rating is untouched, all 44 checksum slots are correct, and the text
slot holds the replacement.

**What this does not show.** Whether Madden 09 loads either image. Nothing was
booted.

---

## 8. Three things a second game broke, and who has to fix them

Adding a second game module is the first time any of this ran with more than
one, and three places assume there is exactly one. **None of them is a defect
in this module**, and none can be fixed from inside it: two live in files the
contract freezes, and the third in the other game's manifest.

### 8.1 The chooser test asserts the studio list has one row

`tests/mod_editor/test_games_chooser.py::test_the_real_ps2_adapter_is_a_studio_row_and_opens_its_studio`
asserts the chooser table equals exactly `["PS2 NFL 2K5 Studio"]`. That was
RC86's acceptance criterion ("`Select other games…` lists `PS2 NFL 2K5 Studio`
alone"); RC87 is the release that changes it. **Fix:** assert the PS2 row is
*present* rather than sole. The file is frozen, so it moves through the
procedure in `GAME_MODULE_CONTRACT.md` §12.

### 8.2 A runtime-module count is compared against one game's manifest

`tests/mod_editor/test_games_contract.py::test_runtime_modules_mirror_the_runtime_gate`
asserts `len(games.runtime_modules()[0]) == len(nfl2k5.manifest.product_modules)`.
`runtime_modules()` is the **union across every hosted game**: 47 now, against
NFL 2K5's own 35. **Fix:** compare the union with the union, or assert each
game's modules are a subset. Also frozen.

### 8.3 NFL 2K5's allowlist patterns claim every path containing "ps2"

Its manifest sets `allowlist_patterns = ["*ps2*", "*xxh3*", "*spu_adpcm*"]`,
which was unambiguous while it was the only PlayStation 2 game. It now matches
**24 of this module's 25 files** — `mod_editor/games/madden09_ps2/*` and
`tools/validate_madden09_ps2_*` both contain "ps2" — so regenerating that
game's `allowlist.fragment.txt` would have it claim files it does not ship.
Two tests see it: the frozen
`test_games_contract::test_allowlist_fragment_mirrors_the_upstream_allowlist`,
whose rule is literally "the fragment is exactly today's ps2 lines", and
`test_games_tooling::test_the_ps2_module_is_in_step_with_the_canonical_files`.

**Fix:** narrow that game's patterns to the paths it owns (its own directory
plus its own `tools/` and `mod_editor/core/` files), and change the frozen
test's rule from "every ps2 line" to "the lines this game's patterns select".
Better still, have `fragments` exclude any path inside another game's package
directory, so the next game does not hit this at all.

This module's own fragment is correct and `fragments madden09_ps2 --check`
passes; the drift is entirely on the other side of the collision.

### 8.4 One that *was* fixable from here

The conformance harness gives each lane a working directory named after its
`lane_id` and shares one root across every hosted game, so two games whose
lanes use the same short id collide on it — a real bug, in frozen
`conformance.py`, that only appears with a second game. This module sidesteps
it by calling its executable-patch lane `gameplay.boot_elf_patches` rather
than `gameplay.executable_patches`; a third game picking a name either module
already uses will hit it again. **Fix:** give each game its own subdirectory
under the conformance work root.

---

## 9. Where the code is

**The module** — `mod_editor/games/madden09_ps2/`:

| file | what it holds |
|---|---|
| `__init__.py` | `GAME`, `IDENTITY`, the fourteen lanes, the studio window spec (the core shell) |
| `__main__.py` | `python -m mod_editor.games.madden09_ps2`: this game alone, with no studio |
| `containers.py` | which `/DATA` files to walk, the `TERF` containers, the preload caches, the synthetic disc |
| `disc_identity.py` | retail vs Deluxe, by boot-ELF digest |
| `inventory_lane.py` | the container inventory (`ReadOnlyLane`) — §3.12 |
| `mmap_art.py` | the `MMAP` layout: parse, decode, index, encode |
| `uniform_art.py` | the art lane itself — catalogue, decode, encode, write-back, verify; container-parameterised, the uniform rows are its defaults — §3.1 |
| `art_pages.py` | the four other art rows: their container lists, the synthetic-disc builder, the CLI — §3.2.2, §3.4, §3.5, §3.6 |
| `team_data.py` | the EA TDB databases: catalogue, writer, verifier — §3.2.1 |
| `identity_lane.py` | the 32 teams' names and colours, in both copies that agree — §3.3 |
| `text_lane.py` | the `TEXT` banks: catalogue, writer, verifier — §3.7 |
| `audio_lane.py` | the `SCHl` streams and `BNKl` banks: catalogue, play, export, bounded stream writer — §3.9 |
| `playbooks_lane.py` | the 102 shipped books and the names inside them — §3.11 |
| `code_patches.py` | executable patches (`CodePatchLane`); the playbook editor caps translated — §3.10 |
| `game.json` · `registry.fragment.json` · `allowlist.fragment.txt` · `pins.json` | the manifest, the mirrors of the canonical registry and allowlist, and this module's own count pins |

**The shared formats** — `mod_editor/games/_formats/`:

| file | what it holds |
|---|---|
| `ea_terf.py` | the container: `TERF`/`DIR1`, `DATA` and `COMP` chunks, the `LZH1` and `RLE1` codecs both ways, member rewrite and rebuild (RC86, plus RC88's encoder) |
| `ea_tdb.py` | the EA TDB v8 reader (RC87), writer and four checksums (RC88), and the four-byte name codec |
| `ea_schl.py` | EA `SCHl` streams and `BNKl` banks: EA-XA and PS ADPCM, both directions (RC88) |
| `ps2_disc/` · `ps2_elf/` | the ISO9660 reader and the ELF32 reader both PS2 modules share |

**The tools** — `tools/`:

| file | what it holds |
|---|---|
| `ps2_iso9660_writer.py` | the bounded image writer: fixed allocation by default, opt-in relocation |
| `ps2_iso9660_verify.py` | the independent verifier, with its own ISO9660 decoder |
| `madden09_ps2_texture_identities.py` | learns the PCSX2 replacement identities by pairing a texture dump with the disc on exact pixels |
| `validate_madden09_ps2_{inventory,uniform_art,uniform_disc_art,art_pages,team_data,identity,text,playbooks,audio,code_patches}.{sh,bat}` | ten shipped-tree validators, one per lane group |

**The tests** — `tests/mod_editor/`, 637 of them, on synthetic data only:

| file | tests |
|---|---:|
| `test_ea_terf.py` | 74 |
| `test_ea_tdb.py` · `test_ea_tdb_writer.py` | 70 · 44 |
| `test_ea_schl.py` | 37 |
| `test_madden09_ps2_module.py` | 2 |
| `test_madden09_ps2_inventory.py` | 14 |
| `test_madden09_ps2_uniform_art.py` | 58 |
| `test_madden09_ps2_art_pages.py` | 33 |
| `test_madden09_ps2_team_data.py` | 43 |
| `test_madden09_ps2_identity.py` | 67 |
| `test_madden09_ps2_text.py` | 44 |
| `test_madden09_ps2_audio.py` | 44 |
| `test_madden09_ps2_playbooks.py` | 52 |
| `test_madden09_ps2_code_patches.py` | 55 |

**The measured evidence** — `docs/product/measured/madden09_ps2/`:
`art-page-textures.json`, `art-page-texture-identities.json`,
`audio_codec_census.json`, `identity_blast_radius.json`,
`pcsx2-texture-identities.json`, `playbook-databases.json`. Counts, sizes,
offsets and digests; no payload. (`measured/` and not `evidence/`: the release
checker forbids a path component named `evidence`.)

The shared format packages are the point: a Madden 08, Madden 12 or NCAA
Football 09 module gets the container, both database halves, the audio codecs
*and* the texture decoder for free — the container reader already opens seven
EA PS2 discs unchanged [M], and `MMAP`, EA TDB and EA `SCHl` are the same on
all of them.

---

## 10. The shipping checklist

`ADDING_A_GAME_MODULE.md`'s last section is the standard a module ships
against — the owner's rule is that the bar set by the first two modules is the
bar for every module after them. Each of its seven points, answered for this
module today: **yes**, **no** with the reason, or a measured **not
applicable**.

**1. Every page has its answer — yes, with one boundary named.** Eleven of the
fourteen pages carry a lane at the highest rung the disc's format permits (§3);
**Build & Share** is the shell's own page and no game writes it; **The Crib** is
an ESPN NFL 2K5 feature that Madden does not have, which is the standard's own
example of a measured reason. **Saves** is the boundary: a Madden 09
memory-card save is a different repository's tooling and this studio works off
the disc, which is a *scope* decision rather than a measurement that the format
cannot support it. It is stated as one in §4 rather than dressed up as one.

**2. Every writer is proved twice — no, on the second half, for every one of
them.** The offline half is met by all eleven writing rows: an independent
verifier that imports none of the writer re-derives the edit from the built
image and checks every byte outside the declared ranges, and **ten of the
eleven have been exercised at least once against the owner's own retail disc**
(§3, §7a) — the eleventh, `rosters.face_textures`, shares its lane class, its
write path and its verifier with four rows that have, and §3.2.2 says that
rather than borrowing their evidence. **The in-game half does not exist for any
writer.** Nothing has been booted, no rebuilt
Madden 09 image has been loaded by the game, and no row is `runtime-proved`.
Every row, receipt and page says so in as many words. By this point the module
is **not complete**, and §7's first item is the whole reason.

**3. Art round-trips — yes on the disc route, no on the pack route.** Textures
decode to PNG and edited PNGs encode back (§3.1); the encoder round-trips real
members byte for byte where the format allows — **1,780 of 1,780 `MMAP` members
and 1,836 of 1,836 `LZH1` members** [M]; and the PCSX2 replacement identities
exist, learned from a real 33-frame texture dump: **3,024** disc textures on
the uniform lane's containers and **234 of 8,449** on the four art pages. The
pack route is **not** shipped: *Write PCSX2 pack* is offered from no row,
because no pack built from those names has been loaded in an emulator (§7.7).

**4. Rosters, team data and text, with the four database CRCs proved against
the disc's own databases before any write is offered — yes.** `verify_crcs` was
run over every TDB on the retail disc before a byte was written with it:
**4,806 of 4,806 slots across 252 databases** when the writers landed, and
**8,926 of 8,926 across all 355** once the four-byte name fix widened what the
reader opens — **0 mismatches** either way [M]. The roster (§3.2.1), identity
(§3.3) and text (§3.7) writers are all `offline-writer-proved`, and each
re-derives all four checksum kinds from the destination's own bytes in a
verifier that imports none of the writer.

**5. Audio, stadiums, playbooks and gameplay patches at the rung their formats
permit — yes, with the measured statements the standard asks for.** Audio: a
stream writer (§3.9) and an `extract-only` bank row whose reason is the 134
undecoded loop points (§4). Stadiums and field art: texture writers, with the
805 `SMF` / 2 `DMF` / 642 `SMF` geometry members counted and left alone because
no decoder for either format exists here (§4). Playbooks: a name and
numeric-field writer over all 102 shipped books, with the exact-size packing
path measured on every one of them (§3.11). Gameplay: five translated words
with per-site disassembly, and the runtime capacity layer measured and
deliberately not shipped (§7.4).
The sub-clause — *"the executable-patch lane carries at least the translations
the community already ships"* — is a measured **not applicable**: PCSX2's
bundled patch archive holds **4,471 entries and none of them is for this
title**; no entry names `38014255`, `084562FF`, `SLUS-21770` or `Madden NFL 09`
[M]. The set to match is empty, and this lane carries five words more than the
community ships.

**6. Validators in a shipped tree, the Windows smoke, evidence paths that
exist — partly; the Windows half is pending the RC88 smoke.** On Linux, in a
staged release tree: `stage_release.py` stages 496 files,
`check_2k5_mod_studio_release.py` prints its PASS line and the staged
`check_2k5_mod_studio_runtime.py` prints its closure PASS at `registry=106`.
All **ten** of the module's validators pass here (`inventory`, `uniform_art`,
`uniform_disc_art`, `art_pages`, `team_data`, `identity`, `text`, `playbooks`,
`audio`, `code_patches`), and the conformance harness passes **544 of 544**
checks for `madden09_ps2`. Registry evidence paths: **yes** — all seventeen
paths the module's fourteen rows cite exist in the tree, and the measured
records moved to `docs/product/measured/` for the release checker's sake.
**A real `cmd.exe` run of the `.bat` validators and the portable build's
Windows smoke have not been run for this candidate**; both happen at release,
and this line is *pending the RC88 smoke*.

**7. Nothing is claimed above its proof — yes.** No row is `unknown`, so
nothing is hidden; the one `extract-only` art row keeps its rung while a
separate row carries the writer; `audio.banks` stays `extract-only` with its
reason; the inventory row writes nothing and says so; §7 lists ten things this
module does not claim, and the first of them is that nothing has been booted.
Every `runtime.status` in the module's fourteen rows is `not-tested` (six
rows) or `not-applicable` (eight), and **no `runtime.evidence` list has a
single entry in it**.

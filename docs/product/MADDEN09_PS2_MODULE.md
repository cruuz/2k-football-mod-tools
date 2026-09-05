# Madden NFL 09 (PlayStation 2) — what the module does today

The second game on the Game Studio shell, and the first written *for* it: the
module ships no window of its own. `studio_window` points at the core shell,
which draws the same fourteen pages every studio has. A lane reaches its page
by being a lane; a page with no lane says why in one sentence.

This document is the honest inventory: what each page does today, what is
measured, what is merely sourced, what is assumed, and — at the end — the list
of things this module deliberately does **not** claim.

**Two pages write now** (§3.3, §3.4) and **nothing has been booted** (§7,
§7a). Every claim about a written image is about its bytes.

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

And one that shapes what is *not* here: **there is no `LZH1` encoder**, in
this repository, in the owner's, or anywhere public [S]. An edited member can
be stored uncompressed — the retail disc itself ships 270 of `UNIFORMS.DAT`'s
725 members that way inside a `COMP` container [M] — but it cannot be
re-packed to its original size. Every writer in this module's future runs into
that, and none of them pretends otherwise.

### 2.1 Container size limit

The module reads a container up to **96 MB** and lists anything larger with
its size, unread. Madden 09's six speech and music containers run 124 MB to
415 MB [M]; counting their members is not worth half a gigabyte of memory, and
"listed but not read" is a state the catalogue names rather than a silent gap.

---

## 3. The pages

The shell's fourteen pages, in its order, and what Madden 09 has on each.

| page | lane | classification | what it does today |
|---|---|---|---|
| Uniforms & Equipment | `uniforms.mmap_export` | `extract-only` | see §3.1 |
| Names, Numbers & Faces | `players_rosters.team_databases` | `offline-writer-proved` | §3.3 — **edits** |
| Text & Team Identity | — | — | page note |
| Field Art & Create-Team Art | — | — | page note |
| Stadiums | — | — | page note |
| Presentation | — | — | page note |
| Menus & UI | `menus.text_members` | `offline-writer-proved` | §3.4 — **edits** |
| The Crib | — | — | page note |
| Audio | — | — | page note |
| Gameplay | `gameplay.executable_patches` | `unknown` | §3.5 — not drawn |
| Playbooks & Plays | — | — | page note |
| All Textures | `textures.container_inventory` | `read-only-mapped` | §3.2 |
| Saves | — | — | page note |
| Build & Share | — | core | the shell's own |

### 3.1 Uniforms & Equipment — the `MMAP` art lane

`ArtLane`, `extract-only`. The disc's uniform, player-face, coach-face and
tattoo textures, catalogued, previewed, exported as PNG, and checked on the
way back in. The pixel layout is **proved** — §6 has the evidence — so this
page exports art rather than only describing it.

**Measured on the retail disc's four art containers** [M]:

```
1,780 texture members
7,616 images
7,082 decodable            (534 refused, in three named groups)
```

Across ten containers, 11,039 of 12,779 images decode. Every refusal falls in
a group the catalogue names rather than a silent gap:

| refused | why |
|---:|---|
| 1,188 | pixels stored under EA codec 4, `IPU1` — every `UIS_MCFL` member and nothing else. Not decoded here. |
| 453 | a palette-only image entry: it carries alternate CLUTs for another image and has no pixels of its own. Not a failure. |
| 99 | no palette — the `PLYRFACE` hairstyle entries, whose colour Madden picks at run time. |

Whole-disc catalogue: **about four minutes** including an export and its verify
[M]. That is the honest cost of decoding 1,780 `LZH1` members in pure Python,
and the reason the studio runs a catalogue in a child process with progress.
Only the *surface* table is at the front of an `MMAP` member — the image,
palette and name tables are past the pixels — so there is no prefix shortcut.

**What the page will not do, and says so.** `replacement_identity` returns
`None`: a PCSX2 replacement filename is built from the GS `TEX0` and CLUT
hashes the emulator computes while drawing, and reading those needs a **GS
dump of Madden 09 running**, which nobody has captured. The *Write PCSX2 pack*
step refuses with that sentence rather than writing a name that would silently
never match. Nothing is written back to the disc either (§7).

**Import is checked, not decorative.** A PNG must be exactly the texture's
size or an exact whole-number multiple, 8-bit, non-interlaced, RGB or RGBA;
anything else is refused naming the size that was wanted. A same-size PNG is
then indexed against the texture's *own* palette and the result reported —
a Madden 09 texture rides its own CLUT, so a colour that palette does not
carry cannot be introduced, and the user is told how many pixels landed
exactly instead of finding out later.

**The export is verified independently.** `verify` re-decodes every exported
texture straight from the user's disc **by key**, not through the catalogue
that produced the receipt, and fails on a tampered file, a missing one or an
undeclared one. A check that trusts the thing it is checking is not one.

**How the textures are grouped, and what is not known.** `PLYRFACE` and
`COACFACE` name their single image `FACE`, and `TATTOOS` names its own [M], so
those groups come from the file. `UNIFORMS.DAT` names **nothing** — 455
members, about fifteen unnamed images each — so the member index is the only
structure it offers, and **which team a member belongs to is not established
here** [A]. The page says that rather than guessing.

### 3.2 All Textures — the container inventory

`ReadOnlyLane`, `read-only-mapped`. Walks every `/DATA` file, opens the ones
that are containers, and lists them: chunk chain, alignment, member count,
codec histogram, and per-member offset, stored size, codec, unpacked size and
post-decompression format.

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
is in `EA_TERF_FORMAT.md` §4.

Whole-disc walk: **about ten seconds** [M].

The lane caps its *target list* at 4,000 rows because a table is a table and
36,195 rows is a data dump; the document's counts stay complete either way.

### 3.3 Names, Numbers & Faces — the team databases

**Writer**, `offline-writer-proved`. Madden 09's team, roster and tuning data
lives in **EA TDB v8 databases packed as `TERF` members** — plus one bare
database, `/DATA/STRMDATA.DB`, with no container around it [M]. The reader is
new and shared: `mod_editor/games/_formats/ea_tdb.py`.

**Measured on the retail disc** [M]:

```
355 databases   (235 in DB_TEAMS.DAT, 104 in GAMEDATA.DAT,
                 15 in TEMPLATE.DAT, 1 bare STRMDATA.DB)
2,151 tables
354,812 records
60,537 field definitions
```

Whole-disc walk: **about nineteen seconds** [M].

The catalogue carries **field names, not field values**. A field name is the
schema and is identical on every disc; a record's contents are the user's game
data. A test asserts the point by searching the serialised catalogue for the
synthetic fixture's own string values and failing if it finds one.

Three things the TDB reader had to get right, each measured rather than
assumed:

- **Records are bit-packed LSB-first**, within the byte and within the field
  [M]. Some documentation of this format says MSB-first; under that reading
  the same bytes give a different team id for every player on one team and the
  same speed rating for all of them. LSB-first was cross-checked against three
  independent existing readers and validated field-by-field against five real
  databases: **2,321 records, 7,797 field definitions, zero mismatches** [M].
- **`version` is the only big-endian field in the header** [M]. Read
  little-endian it comes back 2048; read big-endian, 8. This is why two
  readers can disagree about the version of one file.
- **Strings are latin-1, never utf-8** [M]. EA stores 8-bit characters; a
  utf-8 decoder mangles them or refuses.

**The four checksums, now computed.** EA stores four CRC-32/MPEG-2 values in
every TDB — a file-header CRC over the header's first 20 bytes, a *prior-block*
and a *header* CRC per table, and an end-of-file CRC over the last table's data
— and a Madden save with a stale one is refused by the game outright [S]. The
algorithm was proved before anything was written with it: `verify_crcs` was run
over **every TDB on the retail disc, and the stored value equalled the
recomputed value at 4,806 of 4,806 checksum slots across 252 databases** [M].

| where | databases | slots | mismatches |
|---|---|---|---|
| `DB_TEAMS.DAT` | 235 of 235 members | 3,462 | 0 |
| `TEMPLATE.DAT` | 14 of 15 members | 902 | 0 |
| `GAMEDATA.DAT` | 2 of 104 members | 16 | 0 |
| `STRMDATA.DB` | 1 of 1 | 426 | 0 |
| **total** | **252** | **4,806** | **0** |

The 103 members not counted are refused by the *reader*, not the checksum pass:
each declares a table named `SGF\x00`, and a four-character name with a NUL in
it fails the reader's printable-name rule [M]. That is a reader limitation, it
is not worked around here, and none of those members is in what this lane edits.

**What it writes.** `/DATA/DB_TEAMS.DAT` only, and inside it two tables:

- `PLAY` — first name, last name, jersey number, age, and twenty ratings
  (`POVR PSPD PACC PAGI PSTR PAWR PCTH PCAR PTHP PTHA PJMP PTAK PBTK PPBK PRBK
  PSTA PINJ PKPR PKAC PMOR`). The list is explicit in `PLAYER_FIELDS`, not
  "whatever is numeric", so what the page offers is something a reader can
  check. A rating stops at **99** — the scale the game's own data is on — not
  at the 127 its seven-bit field would hold. A name stops one byte short of its
  field so the terminator survives.
- `TEAM` — `TDNA` nickname, `TLNA` city, `TSNA` abbreviation, `TMNC` short
  name. What each holds was read off the owner's disc (`Bears` / `Chicago` /
  `CHI` / `Brownies` for Cleveland) [M]; no value from that reading is stored
  in this repository.

On the retail disc that is **12,499 editable rows** across 235 databases [M].
Height and weight are deliberately absent: `PWGT` looks like pounds less 160 on
the records sampled, and "looks like" is not a unit this page will label a
spinner with.

**Why it is a bounded write.** A TDB field owns a fixed run of bits in a
fixed-stride record, so a record edit **cannot change a length**. The database
comes back the same size, so the `TERF` member does, so the container does —
measured: `rewrite_member` handed a member's own bytes reproduces
`DB_TEAMS.DAT` byte for byte [M] — so the ISO extent is rewritten in place and
the destination image is the source's exact size. Every one of those four
invariants is checked at build time and refused rather than approximated.

**What stays read-only, and why the disc says so.** `/DATA/GAME.QKL` and
`/DATA/FE.QKL` are preload caches: a `QL01` header, a `FILS` chunk naming 29
and 28 `/DATA` files, and a body carrying at least some of them verbatim — the
first 256 bytes of `UIS_BANR.DAT`, `UNIFORMS.DAT`, `PLYRFACE.DAT`,
`GAMEDATA.DAT`, `TEMPLATE.DAT` and `LOADDATA.DAT` each appear inside the cache
that names them [M]. Editing one copy and not the other would leave the game
reading whichever it reached first, so `containers.preload_names` reads that
list off the user's own image and any container it names is refused.
`DB_TEAMS.DAT` is named in neither [M]. `STRMDATA.DB` is out of scope: it is a
5 MB bare database of league and presentation tables with no `PLAY` table [M].

Not every named file is demonstrably copied — `STADATA.DAT` is named in both
and its head is in neither [A] — so *what* a cache carries of a file it names
is not established. The refusal is deliberately the conservative reading.

**The verifier imports none of the writer.** It runs
`ps2_iso9660_verify.verify_replacement` for the container-level claim, re-parses
the destination's member with the plain reader to read every edited value back,
re-derives all four checksums from the destination's own bytes, and byte-compares
the edited member against the source requiring every differing byte to fall
inside a declared field span or a checksum slot. Its tests prove it fails on a
byte flipped outside the declared ranges, on a record changed behind the
receipt's back *inside* a declared range, and on a stale checksum.

Also measured and recorded rather than used as a bound [M]: `lenBits` is
`lenBytes * 8 - 1` in 561 of 561 tables (it is *not* the last field's end);
index blocks trail the record array rather than preceding it; and `dbSize` is
the last table's end plus four, not the file length.

### 3.4 Menus & UI — the text banks

**Writer**, `offline-writer-proved`. Finds every `TEXT` member — a member whose
decompressed bytes are printable strings separated by NULs — measures it (string
count, longest and mean length, printable ratio, and the SHA-256 of the
decompressed bytes) and rewrites its strings in place.

**Measured on the retail disc** [M]:

```
14,748 TEXT members
14,748 strings          (one string per member)
3,242,117 bytes
```

That member count is exactly the whole-disc census in `EA_TERF_FORMAT.md` §4,
arrived at independently — this lane walks all 101 readable containers rather
than sampling, so the two numbers agreeing is a real cross-check. Whole-disc
walk: **about nine seconds** [M].

**The catalogue carries no string.** The contract's third rule is that a
catalogue holds names, offsets, lengths and digests and never payload, and a
catalogue is a file that can be shipped. So the strings are read from the
*user's own image* on demand, through `TextLane.preview` and the command
line's `--preview`, and are never stored anywhere.

**Why it is fast.** A member has to be unpacked before it can be classified,
but only its **first 32 bytes** — which is all `identify_member` looks at, and
where the codec stops. Only a member that matches is then unpacked in full.
Classifying by full decompression instead ran for over ten minutes on the
retail disc and was abandoned: 36,195 members, 4,269 of them `LZH1` streams
decoded in pure Python, for an answer the head already gave.

**What it writes: a string slot.** One run of characters inside a member,
addressed by its **byte offset** rather than by its position in a split, because
an edit changes how a split comes out and an offset does not. Its *allocation*
is the room up to the next string — the NUL padding a previous edit left
included — so shortening a string does not spend it: the same room is offered
next time. A shorter replacement is padded with the format's terminator; a
longer one is refused with the length it has to fit. The member keeps its exact
byte count, so the container does, so the ISO extent does.

On this disc a bank is usually **one string with no NUL in it**, so its slot is
the whole member and replacing it replaces the whole bank; the label shows the
whole (elided) text and the budget shows the whole allocation, so what is being
replaced is on screen. A finer unit — the pipe-delimited `KEY=value` pairs
`OSDKSTRN.DAT` carries, say — would need that inner grammar decoded, and it has
not been.

**Six of the eight containers are editable.** `GAMEDATA.DAT`, `LOADDATA.DAT` and
`STADATA.DAT` are named in the `FE.QKL` / `GAME.QKL` preload caches and are
refused for the reason §3.3 gives; `OSDKSTRN.DAT`, `STORYMSG.DAT`,
`STRYCPTN.DAT`, `STRYEMAL.DAT`, `STRYHDLN.DAT` and `STRYTEXT.DAT` are named in
neither [M].

**One classifier change, worth 12 members.** `identify_member` calls a member
`TEXT` when its first 32 bytes are printable, which stops being true of a bank
this lane has shortened — two printable bytes and thirty NULs. `is_text_member`
therefore discounts the padding before asking. On the retail disc that finds
**14,760** banks rather than 14,748, and every one of the twelve extra is a
NUL-padded name string in `STADATA.DAT` that the stricter rule was missing [M].
It changes nothing about what the shared reader calls a member; the widened rule
lives in this lane.
### 3.5 Gameplay — executable patches, nothing mapped

`CodePatchLane`, classification **`unknown`**, so the studio draws no editor
for it at all: the page states the classification and the registry's reason.

The pipeline is complete and proved on a synthetic ELF — plan against the
user's own boot ELF (address file-backed, original word as expected), emit a
`.pnach` naming that ELF's own PCSX2 CRC, verify by re-reading both
independently and failing a tampered file. **Every translation is refused by
name.**

The catalogue is six subject areas the owner's Madden 09 static-analysis work
has opened [S] — AI play calling, blocking dominance, blocking intent, catch
and fumble, defensive fatigue, double teams — each carrying the plain
statement that no word has been located for it. A target here is a question,
not a capability.

**No retail address or code byte is in this repository.** What the lane knows
about an executable it reads from the user's own image at run time.

A future PR that locates one site fills in a single `TRANSLATIONS` entry and
changes nothing else. That is what the synthetic proof exists to guarantee.

---

## 4. Pages with no lane, and why

Each has one sentence in `game.json`'s `page_notes`, shown under the shell's
own. In full:

- **Text & Team Identity** — team names and colours live in the `DB_TEAMS.DAT`
  databases, which the Names, Numbers & Faces page already lists; a separate
  identity editor waits on a database writer, and there is none.
- **Field Art & Create-Team Art** — `FIELDART.DAT` holds 642 `SMF` geometry
  members and 73 `MMAP` textures [M]; the textures are reachable through the
  same decoder as the uniforms, and no geometry format is decoded anywhere
  here.
- **Stadiums** — `STADIUMS.DAT` holds 651 `SMF` geometry members and 434
  `MMAP` textures [M]. Same position as field art: the textures are readable,
  the geometry is not decoded, and there is no editor for either yet.
- **Presentation** — the scorebug and broadcast overlays are drawn by the
  executable, and no data file on this disc has been mapped to them.
- **The Crib** — not a Madden concept; it is an ESPN NFL 2K5 feature and this
  page stays empty here on purpose.
- **Audio** — `SOUNDDAT.DAT`, `BGM.DAT` and the speech containers carry EA
  `SCHl` streams and `BNKl` banks; no decoder for either is built here and no
  public writer exists.
- **Playbooks & Plays** — playbook data has not been located on this disc by
  this project, and the owner's own research records that no playbook is among
  the members the `GAME.QKL` preload copies [S].
- **Saves** — a Madden 09 memory-card save is a different repository's
  tooling; this studio works off the disc.

---

## 5. What is measured, in one table

Every number this module quotes about a real disc, and the command that
produced it. All read-only; nothing was written to either image.

| number | value | source |
|---|---|---|
| retail image bytes | 1,657,339,904 | `identify` [M] |
| Deluxe image bytes | 1,846,476,800 | `identify` [M] |
| containers read | 101 of 107 | inventory lane [M] |
| members | 36,195 | inventory lane [M] |
| members classified | 9,063 (256/container sample) | inventory lane [M] |
| `MMAP` members in the sample | 4,901 | inventory lane [M] |
| `TEXT` members in the sample | 1,288 | inventory lane [M] |
| TDB databases | 355 | team-data lane [M] |
| TDB tables | 2,151 | team-data lane [M] |
| TDB records | 354,812 | team-data lane [M] |
| TDB field definitions | 60,537 | team-data lane [M] |
| retail boot ELF PCSX2 CRC | `38014255` | code-patch lane [M] |
| Deluxe boot ELF PCSX2 CRC | `084562FF` | code-patch lane [M] |
| inventory walk | ~10 s | wall clock [M] |
| team-data walk | ~19 s | wall clock [M] |
| `TEXT` members (full walk) | 14,760 | text lane [M] |
| strings in them | 17,822 | text lane [M] |
| their decompressed bytes | 3,242,117 | text lane [M] |
| text walk | ~9 s | wall clock [M] |
| TDB checksum slots verified | 4,806 across 252 databases | `ea_tdb.verify_crcs` [M] |
| of those, mismatching | 0 | `ea_tdb.verify_crcs` [M] |
| editable roster rows | 12,499 | team-data lane [M] |
| team-data catalogue with rows | ~29 s | wall clock [M] |
| texture members (4 art containers) | 1,780 | uniform-art lane [M] |
| images in them | 7,616 | uniform-art lane [M] |
| images that decode | 7,082 | uniform-art lane [M] |
| images refused (3 named groups) | 534 | uniform-art lane [M] |
| uniform-art walk + export + verify | ~4 min | wall clock [M] |

And the same three lanes on the **Deluxe** disc [M], which is the point of
telling the two apart:

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
text banks alone, and the lanes say so without being told.

Reproduce any of them:

```
python3 -m mod_editor.games.madden09_ps2.inventory_lane --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.team_data     --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.text_lane     --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.code_patches  --source "<your>.iso"
```

The two writing lanes take the same command one step further — a recipe in,
a NEW image out, and the independent verifier's verdict printed:

```
python3 -m mod_editor.games.madden09_ps2.team_data --source "<your>.iso" \
    --recipe edits.json --destination new.iso --report receipt.json
python3 -m mod_editor.games.madden09_ps2.text_lane --source "<your>.iso" \
    --recipe edits.json --dry-run
```

Every one of them also runs with no disc at all — `--selftest`, or the five
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

---

## 7. What this module does not claim

Said plainly, because a page that stays quiet about its limits is worse than
one with fewer pages.

1. **Nothing has been booted.** Two lanes now write — the team databases and
   the text banks — and both are `offline-writer-proved` and can go no higher.
   The honest next test is: rebuild a container, put it back in an ISO, boot it
   in PCSX2, see the game load it and see the change on a screen. **That has not
   been run** and cannot be run from this box. Every claim in §3.3 and §3.4 is
   about bytes.
2. **Two lanes still write nothing at all**: the uniform art (which exports and
   imports but does not put an image back on a disc) and the executable patches
   (which emit a `.pnach` beside the image, never into it).
3. **No `LZH1` encoder exists** [S], here or anywhere public. It does not block
   the two writers — the containers they touch store their members
   uncompressed, so a same-size member goes back in its own slot and the
   container comes out byte-identical outside it [M] — but it does block any
   writer that would have to replace a *packed* member, which is most of the
   art containers.
4. **What a preload cache carries is not established** [A]. `GAME.QKL` and
   `FE.QKL` name 29 and 28 files and demonstrably carry six of them verbatim;
   whether they carry all of what they name is unknown, so every named container
   is refused rather than half-written.
5. **The container checksum question is open** [M/A]. No field in any
   container header varies with content in any way the reader could find, and
   the layout rules hold with zero residue across 47,769 members — but that is
   the whole of the search, and it is not proof. The circumstantial evidence
   is good (the community's Deluxe disc rewrites five containers, carries two
   defects the retail disc does not, and still plays [S]); it does not close
   the question.
6. **No PCSX2 replacement identity.** Naming a texture for a replacement pack
   needs the GS TEX0 and CLUT hashes PCSX2 computes at draw time, which come
   from a **GS dump of Madden 09 running on the rig**. No such dump exists.
   `replacement_identity` therefore returns `None` and the *Write PCSX2 pack*
   step refuses with that sentence rather than inventing a filename that would
   silently never match.
7. **No gameplay patch is mapped.** Six subject areas, zero located sites.
8. **`SMF` and `DMF` geometry, `SCHl` audio and `BNKl` banks are identified
   and not decoded.** Knowing a member's magic is not the same as reading it,
   and the module does not blur the two.

---

## 7a. The real-disc trial

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

```
mod_editor/games/madden09_ps2/
  __init__.py         GAME, IDENTITY, the studio window spec (the core shell)
  containers.py       which /DATA files to walk; the synthetic disc
  disc_identity.py    retail vs Deluxe, by boot-ELF digest
  inventory_lane.py   the container inventory (ReadOnlyLane)
  uniform_art.py      the MMAP art lane
  mmap_art.py         the MMAP pixel decoder
  team_data.py        the EA TDB databases: catalogue, writer, verifier
  text_lane.py        the TEXT banks: catalogue, writer, verifier
  code_patches.py     executable patches (CodePatchLane, nothing mapped)
  game.json  registry.fragment.json  allowlist.fragment.txt  pins.json

mod_editor/games/_formats/
  ea_terf.py          the container (RC86; shared)
  ea_tdb.py           the database reader (RC87) and writer (RC88); shared

tools/validate_madden09_ps2_{inventory,uniform_art,team_data,text,code_patches}.{sh,bat}
tools/ps2_iso9660_writer.py  tools/ps2_iso9660_verify.py   the bounded ISO half
tests/mod_editor/test_madden09_ps2_*.py
tests/mod_editor/test_ea_tdb.py  tests/mod_editor/test_ea_tdb_writer.py
```

The shared format packages are the point: a Madden 08, Madden 12 or NCAA
Football 09 module gets both readers *and* the texture decoder for free — the
container reader already opens seven EA PS2 discs unchanged [M], and `MMAP`
and EA TDB are the same on all of them.

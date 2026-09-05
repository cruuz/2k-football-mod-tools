# Madden NFL 09 (PS2) — the Playbooks & Plays page

Status: **built and proved offline on the retail disc**, 2026-09-05.
Classification `offline-writer-proved`. **No rebuilt Madden 09 disc has been
booted**; §8 says exactly what a boot would have to show.

Registry row: `madden09ps2.playbooks.databases`, surface `scripts_config`,
page `playbooks`. Lane: `mod_editor/games/madden09_ps2/playbooks_lane.py`.
Evidence document: `docs/product/measured/madden09_ps2/playbook-databases.json`.
Validators: `tools/validate_madden09_ps2_playbooks.{sh,bat}`.

**Evidence tags.** **[M]** measured here on the owner's retail
`SLUS-21770` image, read-only; **[S]** sourced from the owner's research;
**[A]** assumed.

---

## 1. Where the playbooks are, and why nothing could read them

`/DATA/GAMEDATA.DAT` is a `TERF -> DIR1 -> COMP -> DATA` container, 4,422,400
bytes, 64-byte alignment, **115 members** [M]. 104 of them are EA TDB v8
databases; 102 of those carry the same nineteen tables and are the shipped
playbooks; the two beside them (members 113 and 114) carry only
`ARTL`/`OPTM`/`PSAL` and are the in-game route menus, not playbooks. The other
eleven members are eight `MMAP` UI screens, one 64-byte `TEXT` blob, one empty
member, and one 32,027-byte member this reader does not classify [M].

The nineteen tables, as the file spells them [M]:

```
ARTL FORM PBAI PBAU PBFM PBPL PBST PLCM PLPD PLRD
PLYL PLYS PSAL SETG SETL SETP SGF\x00 SPKF SPKG
```

**`SGF` is followed by a NUL byte**, and that one byte is why this page did not
exist. `ea_tdb.TdbDatabase._name` decoded a four-character name as strict
printable ASCII and refused anything else, so every database declaring that
table was rejected before a single row was read — **103 of the disc's 355**
(the 102 playbooks and `TEMPLATE.DAT` member 13, the create-a-playbook
template). The module's own docstring recorded the consequence as a
measurement: 4,806 checksum sites across 252 databases, "the other 103 members
are refused". The owner's research had already settled that the table is real
(`madden09-iso-contents.md` §7) [S]; the reader simply could not open it.

### The fix, in `mod_editor/games/_formats/ea_tdb.py`

A four-character name is four **bytes**, and EA did not restrict them to
characters. Names are now decoded leniently and rendered unambiguously:

* `decode_name(raw)` — every byte outside `0x20..0x7E` becomes `\xNN`, and a
  literal backslash becomes `\\`. `b"PLAY"` reads `"PLAY"`; `b"SGF\x00"` reads
  `"SGF\\x00"`, which is how a caller addresses the table.
* `encode_name(name)` — the exact inverse, refusing anything that does not come
  back to four bytes. Doubling the backslash is what makes the pair a
  *bijection* rather than merely a rendering, so no two names ever collide.
* `TdbTable.raw_name` / `TdbField.raw_name` keep the four bytes the file
  actually held, and `name_bytes` hands a writer those bytes rather than a round
  trip through text. `build_tdb` writes `name_bytes`, so a synthetic table named
  `SGF\x00` parses → writes → parses identical.
* The refusal that used to catch a directory read at the wrong offset is kept,
  weakened to exactly what the corpus supports: a name with **no** printable
  byte at all is still refused, by the same sentence.

### The disc proof

Read-only pass over every database on the retail image, before and after:

| | before the fix | after the fix |
|---|---:|---:|
| databases that parse | 252 | **355** |
| databases refused | 103 | **0** |
| tables | — | 4,108 |
| field definitions | — | 85,400 |
| checksum sites | 4,806 | **8,926** |
| checksum sites wrong | 0 | **0** |

In `GAMEDATA.DAT` alone: **104 of 104 databases parse, 4,096 checksum slots,
0 mismatches** [M]. Across all 89,508 table and field names on the disc the
**only** byte outside `0x20..0x7E` anywhere is that one trailing NUL
(103 occurrences of `53 47 46 00`), and **no name carries a backslash** [M] —
so the backslash escape is a safety property rather than something the corpus
exercises.

The independently-derived corroboration: this lane's own catalogue over the 102
books reports 670,263 records, and its per-table totals match the owner's
`madden09-tdb-schema.md` appendix A.3 **table for table** — `ARTL` 29,123,
`PLYS` 243,133, `PSAL` 119,396, `PBAI` 77,134, `SETG` 62,819, `SETP` 26,422,
`PBPL` 22,105, `PLYL` 22,103, `SGF\x00` 17,630, `SPKG` 17,064, `SPKF` 8,992,
`PLPD` 7,651, `PLCM` 4,332, `PLRD` 4,314, `SETL` 2,402, `PBST` 2,300, `PBAU`
1,424, `FORM` 1,000, `PBFM` 919 [M].

---

## 2. What the page edits, and what it does not

### 2.1 The string fields — all eight of them

Eight of the nineteen tables carry a `STRING` field called `name`, and every one
is offered. Widths are read out of each file's own field directory, never
written down; the numbers below are the retail schema [M]:

| table | rows on the disc | `name` width | what the row is |
|---|---:|---:|---|
| `FORM` | 1,000 | 18 B (17 chars) | a formation |
| `PBFM` | 919 | 18 B (17 chars) | this book's copy of a formation |
| `PBST` | 2,300 | 19 B (18 chars) | this book's copy of a set |
| `SETL` | 2,402 | 23 B (22 chars) | a set — the personnel and alignment under a formation |
| `SGF\x00` | 17,630 | 4 B (3 chars) | a set group |
| `PBPL` | 22,105 | 21 B (20 chars) | this book's copy of a play |
| `PLYL` | 22,103 | 31 B (30 chars) | a play |
| `SPKF` | 8,992 | 16 B (15 chars) | a special-teams formation |

One byte of each field is the terminator, so the character budget is the width
less one; that is the number the editor shows and `check_edit` enforces.

The **eleven tables with no string at all** are `ARTL`, `PBAI`, `PLCM`, `PLPD`,
`PLRD`, `PLYS`, `PSAL`, `SETG`, `SETP`, `SPKG` and `PBAU` [M] — measured by
reading the type of every field of every table, not assumed from the names.

### 2.2 The numeric fields — six, each with a source

A numeric field is offered only where the owner's research says what it means.

| field | width | meaning | source |
|---|---:|---|---|
| `FORM.FTYP` | 4-bit UINT | formation type: 1 offence, 2 kickoff, 3 safety kickoff, 11 defence, 12 kick return, 13 safety kick return | `madden09-iso-contents.md` §6 [S] |
| `PBFM.FTYP` | 4-bit UINT | the same enum, on the book's copy | as above [S] |
| `PBAU.FTYP` | 4-bit UINT | the same enum, on an audible row | as above [S] |
| `PBAU.PBAU` | 3-bit UINT | which of the formation's audible slots the row fills | the table's own column name [A] |
| `PLYL.risk` | 5-bit UINT | the play's risk rating | `tools/madden_play.py`'s `PLYL` column map [S] |
| `PLYL.motn` | 1-bit UINT | whether the play sends a man in motion | as above [S] |

**Everything else is deliberately not offered.** `PBPL.PLYL`, `PLYS.PSAL`,
`SETL.FORM` and their kind are foreign keys into the play graph; `ARTL`'s twelve
route points, `PBAI`'s AI weights and `PSAL`'s step chains are the geometry and
the assignment language. A renamed play is a bounded change. A re-pointed
foreign key is a dangling reference nobody has booted, so the page does not draw
a control for one.

### 2.3 No row is added or removed

**Every table in every shipped book has `record_count == max_records` —
1,938 of 1,938 across the 102 books, and 1,944 of 1,944 across all 104
`GAMEDATA.DAT` databases** [M], reproducing the owner's own count exactly.
There is no spare slot anywhere on the disc.

Adding a play therefore means growing a table, which is the **editor caps in the
boot executable** — a different code path and a different capability row:
`madden09ps2.gameplay.executable_patches` on the **Gameplay** page, which raises
the `sltiu` immediates at `0x00709468` / `0x00709520` / `0x006D2890`. That row
is the route for *adding*; this one is the route for *renaming*. Neither claims
the other's evidence.

### 2.4 The book has no name, and that is a measurement

A playbook target is labelled by the container member it is
(`GAMEDATA.DAT member 67`) because **the disc gives a playbook no name of its
own** [M]. Three places were looked at and none holds one:

* **inside the book** — no table has a book-level name column; the eight `name`
  fields all belong to a formation, a set, a group or a play;
* **beside the books** — `GAMEDATA.DAT`'s only `TEXT` member is a 64-byte
  `Xbe8…` blob, and its eight `MMAP` members are UI screens;
* **elsewhere on the image** — a raw scan finds two short string tables whose
  entries read like book names, and neither is one: both are the AI
  *coaching-philosophy* and gameplan lists, one in the boot ELF beside the
  team/coach text and one in the story generator's bank, and they run to nine
  and thirteen entries rather than 102. `DB_TEAMS.DAT`'s `TEAM` table carries
  no playbook column either — its 65 fields are ids, colours and team
  ratings.

So a book is described by what it holds — its formation, set and play counts —
and the row targets inside it carry the names the file does have, read from the
user's own image at catalogue time and never written into this repository.

### 2.5 The catalogue, on the retail disc

102 book targets, 1,938 table targets and **78,875 editable row targets**;
32 s to build, 129 MB peak RSS [M].

| table | editable rows |
|---|---:|
| `PBPL` | 22,105 |
| `PLYL` | 22,103 |
| `SGF\x00` | 17,630 |
| `SPKF` | 8,992 |
| `SETL` | 2,402 |
| `PBST` | 2,300 |
| `PBAU` | 1,424 |
| `FORM` | 1,000 |
| `PBFM` | 919 |

---

## 3. Packing: two paths, and which one the disc takes

A record edit never changes a database's length — a TDB field owns a fixed run
of bits in a fixed-stride record — so the **only** thing that can move the
container's directory is the size of the re-encoded `LZH1` member.

**The exact-size path.** The member is re-encoded under a byte budget equal to
the bytes it already occupies. When the stream fits it is padded with NULs to
exactly that size and spliced in place. Every directory word — the member's
offset, its stored size, its codec and its decompressed size — is then unchanged
*by construction*: no other member moves, the container keeps its length, the
ISO extent is rewritten in place, and the preload caches' copies of the
directory stay correct without being touched.

Padding is safe because a bounded decode never reads it: `lzh1_decompress` stops
as soon as it has produced the declared number of bytes, which happens at the
end of the block and before the trailing NULs. Measured, not assumed —
**all 102 shipped books padded to EA's stored size decode back byte-identical**
[M], and the writer re-decodes every stream it pads before it splices it, so a
counter-example is a refusal rather than a bad image.

**The growth path.** When the stream does not fit,
`ea_terf.plan_member_rewrite` chooses the codec and `ea_terf.rewrite_member`
lays the container out again; the ISO writer is given `allow_growth`, and both
copies of the directory in `FE.QKL` are rewritten with it (§4).

### How much headroom there actually is

Every shipped playbook re-encoded and compared against the bytes EA stored [M]:

| | value |
|---|---|
| books measured | 102 |
| books whose re-encode fits its own slot | **102 of 102** |
| smallest headroom | **263 bytes** |
| largest headroom | 4,023 bytes |
| our bytes ÷ EA's bytes | 0.938 – 0.958 |
| padded stream decodes back identical | 102 of 102 |

Our encoder is 4.2 % to 6.2 % smaller than EA's on every book, so the exact-size
path is the ordinary case by a wide margin. It is not *guaranteed* — a rename
that adds entropy can cost more than the headroom — which is why
`fixed_allocation` is `False`, the growth path exists, and the receipt names
which path each member took.

---

## 4. The preload caches: a member-level rule, not a container-level refusal

`GAMEDATA.DAT` is named in **both** `/DATA/GAME.QKL` and `/DATA/FE.QKL`, so the
container-level refusal the sibling database lane uses (`team_data`, which
refuses `TEMPLATE.DAT` and `GAMEDATA.DAT` outright) would refuse every playbook.
The rule here is finer, and it is read off the user's own image through
`containers.preload_copies` rather than written down:

| cache | what it carries of `GAMEDATA.DAT` [M] |
|---|---|
| `GAME.QKL` | byte copies of **members 103–112** — the UI screens at the end of the container — and **no copy of the directory** |
| `FE.QKL` | **two copies of the container's directory** (its first `data_offset` = 1,984 bytes) at 0x298140 and 0x334600, and **no members** |

Two consequences, and the lane encodes both:

1. **No playbook is cached.** Members 0–101 appear in neither cache, which is
   what makes them writable at all. A member that *is* cached is refused by name
   (`_writable_reason`), because a cached copy is a fixed slot and a member
   rewritten at a new size could not be kept in step with it. The retail disc
   never triggers this; the test suite builds a synthetic disc that does.
2. **A changed directory must be mirrored into both `FE.QKL` copies.** On the
   exact-size path the directory does not change and neither cache is rewritten
   at all. On the growth path both copies are written with the new directory —
   the same code path `uniform_art.UniformDiscArtWriteLane` uses for
   `UNIFORMS.DAT` — and a directory that changed *length* is refused rather than
   written past the end of somebody else's copy.

The verifier re-derives this from the destination image alone: it re-reads the
caches there and compares every copy against the container as it now stands, so
a receipt that forgot a copy fails rather than being believed.

---

## 5. The write path, end to end

```
decode the LZH1 member  ->  ea_tdb.parse_tdb
edit the record         ->  ea_tdb.write_records   (fixed length, CRCs recomputed)
check the checksums     ->  ea_tdb.verify_crcs     (refuse if any is stale)
re-encode               ->  ea_terf.lzh1_compress(budget = the member's stored size)
   fits  -> pad to the slot, splice in place, directory unchanged
   fails -> ea_terf.plan_member_rewrite / rewrite_member, mirror FE.QKL's two copies
write the image         ->  tools/ps2_iso9660_writer.replace_files(allow_growth=grew)
verify                  ->  playbooks_lane.verify_build   (imports none of the writer)
```

The verifier proves six things and trusts the receipt for none of them:

1. outside the declared byte ranges the destination *is* the source, and no
   untouched file's extent moved (`tools/ps2_iso9660_verify`, its own ISO9660
   decoder);
2. every edited value **reads back** out of the destination's own container,
   member, table, record and field;
3. inside each edited database every byte that differs from the source lies in a
   declared field span or a checksum slot;
4. all four kinds of TDB checksum agree with the bytes that are there;
5. every member the recipe did not name is byte-identical, still packed;
6. every copy a preload cache carries of the container still equals what it
   copies.

---

## 6. The real-disc trial

Source: the owner's retail `SLUS-21770` image, opened read-only. Destination:
scratch, deleted immediately after. Edit: **`GAMEDATA.DAT` member 67 — the
deepest shipped book, 346 plays over 13 formations — `SETL` record 0, the name
field.**

| | |
|---|---|
| packing path | **exact-size** |
| EA's stored bytes for the member | 67,149 |
| our re-encoded stream | 63,166 |
| padding written | 3,983 NULs |
| container directory changed? | **no** |
| preload caches rewritten | **0** |
| declared ranges | 8 bytes at 538,812 (`dirrec_length:/DATA/GAMEDATA.DAT`) + 4,422,400 bytes at 1,052,076,032 (`extent:/DATA/GAMEDATA.DAT`) |
| source image | 1,657,339,904 bytes |
| destination image | **1,657,339,904 bytes** — the same |
| catalogue / plan / build / verify | 28 s / 2 s / 65 s / 20 s |

Verifier verdict: **PASS** — 1 value read back, 1 playbook re-parsed with
**40 checksum slots all correct**, **114 untouched members byte-identical**,
**12 preload-cache copies still equal to what they copy** (`FE.QKL`'s two
directory copies and `GAME.QKL`'s ten member copies), **0 undeclared changed
bytes**, and `ps2_iso9660_verify` comparing **1,652,917,496 unchanged bytes**
across the two images. Reading the destination back independently — a fresh
`open_disc` → `load_container` → `parse_tdb` — returns the new name and
0 checksum mismatches.

---

## 7. What CI proves, with no game data

`synthetic_source` builds a `SLUS-21770`-shaped ISO carrying a synthetic
`GAMEDATA.DAT`: a `COMP` TERF whose three playbook members are packed with
`ea_terf.lzh1_compress`, followed by a stored member standing in for the UI
screens, plus two `QL01` preload caches from
`containers.build_synthetic_preload_cache` in the shape the disc has — `FE.QKL`
with **two directory copies**, `GAME.QKL` with **one member copy**. Each
synthetic book is a real nineteen-table playbook including a table named
`SGF\x00`, so a reader that cannot decode that name fails in CI rather than only
on a disc CI does not have. Every byte of it is computed from the format's
rules; nothing is copied from a game.

`conformance_edits` renames **a formation and a set**, which on the synthetic
fixture lands on the **growth** path — so the conformance harness exercises
`plan_member_rewrite`, `rewrite_member` and the `FE.QKL` mirroring on every run.
`tests/mod_editor/test_madden09_ps2_playbooks.py` pins the **exact-size** path
separately (a rename to a string the payload already carries), the member-level
cache refusal (a synthetic disc that *does* cache a playbook), a stale cache copy
failing the verifier, and a value changed behind the receipt's back.

---

## 8. What still needs a boot

Everything in this document is bytes. The runtime witness this lane does not
have, and cannot get offline:

* **The owner opens the edited playbook in-game and reads the renamed set.**
  Boot the rebuilt image in PCSX2, choose that book on the play-call screen, and
  see the new name where the old one was. That is the whole claim.
* Second, on the same boot: that the **rest of the book still works** — the
  formations list, the plays under the renamed set, and the CPU calling from it —
  because a re-packed member is a new byte stream even when the directory is
  untouched.
* Third, if a future edit takes the **growth path** on a real disc: that the
  game still loads after `FE.QKL`'s directory copies have been rewritten. The
  retail books all fit their own slots, so no shipped edit has needed it yet.

Until then the row stays `offline-writer-proved` and says so on the page.

**Adding plays is not this page.** The editor caps live in the boot executable
and are raised by `madden09ps2.gameplay.executable_patches` on the Gameplay
page; that route has its own document, its own evidence and its own boot to
earn.
